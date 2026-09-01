import {
  AgentCoreApplication,
  AgentCoreMcp,
  AgentCorePaymentManager,
  AgentCorePaymentConnector,
  type AgentCoreProjectSpec,
  type AgentCoreMcpSpec,
  type CustomJWTAuthorizerConfig,
  type HarnessDeploymentConfig,
} from '@aws/agentcore-cdk';
import { CfnOutput, Stack, type StackProps } from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

/**
 * Harness deployment config: role-scoped fields (for IAM role + container build)
 * plus the full validated spec + its config directory so the L3 construct can
 * synthesize the AWS::BedrockAgentCore::Harness resource.
 */
export type HarnessConfig = HarnessDeploymentConfig;

export interface PaymentConnectorSpec {
  name: string;
  provider: 'CoinbaseCDP' | 'StripePrivy';
  credentialProviderArn: string;
}

export interface PaymentSpec {
  name: string;
  description?: string;
  authorizerType: 'AWS_IAM' | 'CUSTOM_JWT';
  authorizerConfiguration?: { customJWTAuthorizer: CustomJWTAuthorizerConfig };
  autoPayment?: boolean;
  paymentToolAllowlist?: string[];
  networkPreferences?: string[];
  connectors: PaymentConnectorSpec[];
}

export interface AgentCoreStackProps extends StackProps {
  /**
   * The AgentCore project specification containing agents, memories, and credentials.
   */
  spec: AgentCoreProjectSpec;
  /**
   * The MCP specification containing gateways and servers.
   */
  mcpSpec?: AgentCoreMcpSpec;
  /**
   * Credential provider ARNs from deployed state, keyed by credential name.
   */
  credentials?: Record<string, { credentialProviderArn: string; clientSecretArn?: string }>;
  /**
   * Harness role configurations.
   */
  harnesses?: HarnessConfig[];
  /**
   * Parsed connectorParameters for non-S3 KB data sources, keyed by
   * connectorConfigFile path. Forwarded to AgentCoreApplication.
   */
  connectorParametersByFile?: Record<string, Record<string, unknown>>;
  /**
   * Payment specifications with resolved credential provider ARNs.
   */
  paymentSpec?: PaymentSpec[];
}

function toCdkId(name: string): string {
  return name.replace(/_/g, '');
}

/**
 * SetuHaul, issue #92 — the SSM hydration grant, expressed once, in IaC.
 *
 * The runtime hydrates its own environment at cold start by reading the `/setuhaul/*` parameters
 * listed in `backend/app/assistant/agentcore_main.py::_SSM_ENV`. Without that read it has no
 * `DATABASE_URL` and no LLM credential, so it boots, accepts an invoke, and answers
 * `"Database is not configured on the Runtime."` — a 502 to the caller.
 *
 * The grant is on the PATH, not on an enumerated list of names, deliberately: `_SSM_ENV` grows
 * (it gained `/setuhaul/gcp-project` and `/setuhaul/gcp-sa-key` for #103), and a name-by-name
 * grant would need editing in lockstep with application code or produce this same outage in
 * miniature, one parameter at a time.
 *
 * Which regions, and why two:
 *   • `ap-south-1` is the region the runtime actually reads. `_hydrate_ssm_into_env` resolves
 *     `AWS_REGION || AWS_DEFAULT_REGION || DESIGNED_AWS_REGION`; `agentcore/agentcore.json` pins
 *     `AWS_REGION=ap-south-1` as a runtime env var and `settings.DESIGNED_AWS_REGION` is the same
 *     string, so all three paths resolve there. Confirmed empirically, not just by reading: the
 *     2026-09-01 hot-fix that restored chat granted exactly this ARN.
 *   • `us-east-1` is granted alongside it because E7.1's migration is genuinely unfinished — the
 *     same eight parameters still exist there, the retired `us-east-1` runtime is still the
 *     recorded rollback target, and `docs/scripts/put_hosting_ssm.py` still writes to `us-east-1`
 *     ONLY (a live divergence, tracked separately). Remove the `us-east-1` entry when E7.1's
 *     decommission item (#45) closes — not before, or a rollback loses its secrets exactly the
 *     way this incident did.
 *
 * Both entries are the same parameter path in the same account, so the second region widens the
 * blast radius by nothing an operator could not already reach.
 */
const SETUHAUL_SSM_HYDRATE_REGIONS = ['ap-south-1', 'us-east-1'];

/** Matches `_SSM_ENV`'s shared prefix. Every name it reads is `/setuhaul/<key>`, one level deep. */
const SETUHAUL_SSM_PARAMETER_PREFIX = 'setuhaul/*';

/**
 * Decide whether a deployed runtime should receive payment env vars + IAM grants.
 * Payments today only ships a runtime shim for Python HTTP runtimes; injecting
 * AGENTCORE_PAYMENT_* env vars into TypeScript / MCP / A2A / AGUI runtimes
 * would surface env vars they cannot consume and would dilute least-privilege
 * IAM grants for runtimes that never call ProcessPayment.
 */
function isPaymentEligibleAgent(agent: { entrypoint?: string; protocol?: string }): boolean {
  if (agent.protocol && agent.protocol !== 'HTTP') {
    return false;
  }
  const entrypoint = typeof agent.entrypoint === 'string' ? agent.entrypoint : '';
  const entrypointFile = entrypoint.split(':')[0] ?? '';
  return entrypointFile.endsWith('.py');
}

/**
 * CDK Stack that deploys AgentCore infrastructure.
 *
 * This is a thin wrapper that instantiates L3 constructs.
 * All resource logic and outputs are contained within the L3 constructs.
 */
export class AgentCoreStack extends Stack {
  /** The AgentCore application containing all agent environments */
  public readonly application: AgentCoreApplication;

  constructor(scope: Construct, id: string, props: AgentCoreStackProps) {
    super(scope, id, props);

    const { spec, mcpSpec, credentials, harnesses, connectorParametersByFile, paymentSpec } = props;

    // Create AgentCoreApplication with all agents and harness roles
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const appProps: Record<string, unknown> = { spec };
    if (harnesses?.length) {
      appProps.harnesses = harnesses;
    }
    if (connectorParametersByFile && Object.keys(connectorParametersByFile).length > 0) {
      appProps.connectorParametersByFile = connectorParametersByFile;
    }
    if (credentials) {
      appProps.credentials = credentials;
    }
    this.application = new AgentCoreApplication(this, 'Application', appProps as any);

    // === SetuHaul, issue #92 — SSM hydration grant. DO NOT re-apply this by hand. ===
    //
    // Incident, 2026-09-01: THIS stack's own deploy recreated the runtime execution role and
    // silently wiped an `ssm:GetParameter` policy that had been attached by hand during the E7.1
    // region migration. `agentcore deploy` reported success; the runtime came up; every
    // `/setuhaul/*` lookup logged `ssm hydrate miss` + AccessDenied; chat 502'd with "Database is
    // not configured on the Runtime." Nothing errored at deploy time. That is the whole point of
    // moving the grant here: a hand-patched policy on an IaC-managed role is a time bomb whose
    // fuse is the next `agentcore deploy`.
    //
    // Confirmed read-only on 2026-09-02, before writing this: the CDK-managed DefaultPolicy on the
    // live execution role contains no SSM action of any kind, and the hand-applied
    // `SetuHaulSsmHydrate` inline policy is still the only thing granting the read. Once a deploy
    // carries this block, delete that orphan — deploy/README.md has the ordered steps.
    //
    // See SETUHAUL_SSM_HYDRATE_REGIONS above for the region determination and why us-east-1 is
    // still listed. Grant shape is deliberately read-only and path-scoped: this role must never
    // be able to write a secret, only read the ones it hydrates.
    for (const env of this.application.environments.values()) {
      // `runtime.addToPolicy` rather than `runtime.role.addToPrincipalPolicy` (which the payments
      // block below uses): for an *imported*, immutable execution role the vendor construct emits
      // a synth-time warning naming the grants that must already be present, instead of dropping
      // them silently. A silently dropped grant is precisely the failure this block exists to
      // prevent, so the noisier API is the correct one here.
      env.runtime.addToPolicy(
        new iam.PolicyStatement({
          sid: 'SetuHaulSsmHydrateRead',
          actions: ['ssm:GetParameter', 'ssm:GetParameters', 'ssm:GetParametersByPath'],
          resources: SETUHAUL_SSM_HYDRATE_REGIONS.map(region =>
            this.formatArn({
              service: 'ssm',
              region,
              resource: 'parameter',
              resourceName: SETUHAUL_SSM_PARAMETER_PREFIX,
            })
          ),
        })
      );

      // kms:Decrypt is a no-op today, and is included on purpose.
      //
      // Verified against current AWS documentation (KMS developer guide, "Setting permissions to
      // encrypt and decrypt parameter values"), not from memory: SecureStrings encrypted under the
      // default AWS-managed `aws/ssm` key are decryptable by every principal in the account, and
      // you cannot write an access-control policy for that key at all. Confirmed live read-only on
      // 2026-09-02: every `/setuhaul/*` parameter is `Type=SecureString` with `KeyId=alias/aws/ssm`
      // — which is precisely why the 2026-09-01 hot-fix worked with SSM actions alone despite all
      // of them being encrypted.
      //
      // The moment any of them is re-keyed to a customer-managed key — `/setuhaul/gcp-sa-key`
      // being the obvious first candidate — `GetParameter(WithDecryption=True)` starts requiring
      // kms:Decrypt on that key, and #92's exact failure mode returns: a successful deploy, a
      // booting container, and AccessDenied on every hydrate. The `kms:ViaService` condition keeps
      // this from being a general decrypt grant: the key is usable only through SSM, in the two
      // regions the runtime ever reads from.
      env.runtime.addToPolicy(
        new iam.PolicyStatement({
          sid: 'SetuHaulSsmHydrateDecrypt',
          actions: ['kms:Decrypt'],
          resources: ['*'],
          conditions: {
            StringEquals: {
              'kms:ViaService': SETUHAUL_SSM_HYDRATE_REGIONS.map(region => `ssm.${region}.amazonaws.com`),
            },
          },
        })
      );
    }

    // Create AgentCoreMcp if there are gateways configured
    if (mcpSpec?.agentCoreGateways && mcpSpec.agentCoreGateways.length > 0) {
      new AgentCoreMcp(this, 'Mcp', {
        projectName: spec.name,
        mcpSpec,
        agentCoreApplication: this.application,
        credentials,
        projectTags: spec.tags,
      });
    }

    // Create payment infrastructure via CFN constructs
    if (paymentSpec && paymentSpec.length > 0) {
      for (const payment of paymentSpec) {
        const mgrId = toCdkId(payment.name);
        const manager = new AgentCorePaymentManager(this, `Payment${mgrId}`, {
          projectName: spec.name,
          name: payment.name,
          authorizerType: payment.authorizerType,
          description: payment.description,
          authorizerConfiguration: payment.authorizerConfiguration,
          tags: spec.tags,
        });

        const prefix = `AGENTCORE_PAYMENT_${payment.name.toUpperCase().replace(/-/g, '_')}`;

        // Wire env vars from construct output tokens into eligible agent environments only.
        // See isPaymentEligibleAgent — non-Python or non-HTTP runtimes have no shim that
        // can consume these env vars, and giving them sts:AssumeRole on the
        // ProcessPaymentRole would broaden the privilege surface unnecessarily.
        for (const env of this.application.environments.values()) {
          if (!isPaymentEligibleAgent(env.agent)) {
            continue;
          }
          env.runtime.addEnvironmentVariable(`${prefix}_MANAGER_ARN`, manager.paymentManagerArn);
          env.runtime.addEnvironmentVariable(`${prefix}_PROCESS_PAYMENT_ROLE_ARN`, manager.processPaymentRoleArn);

          // Grant runtime execution role permission to assume the ProcessPaymentRole.
          // The ProcessPaymentRole's trust policy allows AccountRootPrincipal, but the
          // caller still needs sts:AssumeRole on its own role to perform the assumption.
          env.runtime.role.addToPrincipalPolicy(
            new iam.PolicyStatement({
              actions: ['sts:AssumeRole'],
              resources: [manager.processPaymentRoleArn],
            })
          );

          // Grant payment data-plane actions directly to the runtime role.
          //
          // NOTE: This deviates from the canonical role model in the AgentCore Payments
          // beta guide, which assigns Get/List/Create instrument+session actions to a
          // separate ManagementRole and limits the agent's role to ProcessPayment only.
          // The current SDK plugin (AgentCorePaymentsPlugin.generate_payment_header)
          // calls GetPaymentInstrument internally during the 402 auto-pay path, so the
          // runtime role needs read access. CreatePaymentSession is included so
          // `agentcore invoke --auto-session` works without a separate ManagementRole
          // call. Tighten this if the SDK is updated to accept pre-fetched instrument
          // details and split create-session into a backend-only flow.
          env.runtime.role.addToPrincipalPolicy(
            new iam.PolicyStatement({
              actions: [
                'bedrock-agentcore:GetPaymentInstrument',
                'bedrock-agentcore:ListPaymentInstruments',
                'bedrock-agentcore:GetPaymentInstrumentBalance',
                'bedrock-agentcore:GetPaymentSession',
                'bedrock-agentcore:ListPaymentSessions',
                'bedrock-agentcore:CreatePaymentSession',
                'bedrock-agentcore:ProcessPayment',
              ],
              resources: [manager.paymentManagerArn, `${manager.paymentManagerArn}/*`],
            })
          );

          if (payment.autoPayment !== undefined) {
            env.runtime.addEnvironmentVariable(`${prefix}_AUTO_PAYMENT`, String(payment.autoPayment));
          }
          if (payment.paymentToolAllowlist) {
            env.runtime.addEnvironmentVariable(`${prefix}_TOOL_ALLOWLIST`, payment.paymentToolAllowlist.join(','));
          }
          if (payment.networkPreferences) {
            env.runtime.addEnvironmentVariable(`${prefix}_NETWORK_PREFERENCES`, payment.networkPreferences.join(','));
          }
          if (payment.authorizerType === 'CUSTOM_JWT') {
            env.runtime.addEnvironmentVariable(`${prefix}_AUTH_MODE`, 'bearer');
          }
        }

        // Create connectors for this manager
        for (const connector of payment.connectors) {
          const connId = toCdkId(connector.name);
          const conn = new AgentCorePaymentConnector(this, `Payment${mgrId}${connId}`, {
            projectName: spec.name,
            paymentManager: manager,
            connectorName: connector.name,
            connectorType: connector.provider,
            credentialProviderArn: connector.credentialProviderArn,
          });

          // Wire first connector's ID as env var (eligible agents only)
          if (connector === payment.connectors[0]) {
            for (const env of this.application.environments.values()) {
              if (!isPaymentEligibleAgent(env.agent)) continue;
              env.runtime.addEnvironmentVariable(`${prefix}_CONNECTOR_ID`, conn.paymentConnectorId);
            }
          }

          new CfnOutput(this, `Payment${mgrId}${connId}ConnectorId`, {
            value: conn.paymentConnectorId,
          });
        }

        // CFN Outputs for post-deploy state parsing
        new CfnOutput(this, `Payment${mgrId}ManagerArn`, {
          value: manager.paymentManagerArn,
        });
        new CfnOutput(this, `Payment${mgrId}ManagerId`, {
          value: manager.paymentManagerId,
        });
        new CfnOutput(this, `Payment${mgrId}ProcessPaymentRoleArn`, {
          value: manager.processPaymentRoleArn,
        });
        new CfnOutput(this, `Payment${mgrId}ResourceRetrievalRoleArn`, {
          value: manager.resourceRetrievalRoleArn,
        });
      }
    }

    // Stack-level output
    new CfnOutput(this, 'StackNameOutput', {
      description: 'Name of the CloudFormation Stack',
      value: this.stackName,
    });
  }
}
