import { useState } from 'react'

import { Button } from '@/shared/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui/dialog'
import { Label } from '@/shared/ui/label'
import { RadioGroup, RadioGroupItem } from '@/shared/ui/radio-group'
import {
  CANCEL_REASON_CODES,
  RESOLVE_REASON_CODES,
  type CancelReasonCode,
  type ResolveReasonCode,
} from '../lib/types'

/**
 * `screens.md` prompts 15a/15b, Flow 6. Both terminal actions require a reason before committing
 * -- the backend enforces this server-side (422 `INVALID_REASON_CODE`), so the picker's
 * controlled vocabulary is a real contract, not a client-side courtesy.
 *
 * Resolve has exactly one reason code (`ISSUE_FIXED`) -- the commit button is genuinely
 * `aria-disabled` until it is selected (U83 Disabled tier: nothing to explain by activating it,
 * a reason is simply required), matching `components.md` foundations section 18.
 */
export function ResolveDialog({
  open,
  onOpenChange,
  onConfirm,
  busy,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (reasonCode: ResolveReasonCode) => void
  busy?: boolean
}) {
  const [reason, setReason] = useState<ResolveReasonCode | null>(null)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Resolve escalation</DialogTitle>
        </DialogHeader>

        <RadioGroup
          value={reason ?? undefined}
          onValueChange={(v) => setReason(v as ResolveReasonCode)}
        >
          {RESOLVE_REASON_CODES.map((code) => (
            <div key={code} className="flex items-center gap-2">
              <RadioGroupItem value={code} id={`resolve-${code}`} />
              <Label htmlFor={`resolve-${code}`}>The underlying issue is fixed</Label>
            </div>
          ))}
        </RadioGroup>

        <DialogFooter>
          <Button variant="neutral" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="constructive"
            aria-disabled={reason === null || busy}
            title={reason === null ? 'Choose a reason first.' : undefined}
            onClick={() => {
              if (reason === null || busy) return
              onConfirm(reason)
            }}
          >
            Resolve
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

const CANCEL_LABELS: Record<CancelReasonCode, string> = {
  SHIPMENT_CANCELLED: 'Shipment cancelled elsewhere',
  DUPLICATE: 'Duplicate of another open escalation',
  CREATED_IN_ERROR: 'Created in error',
}

export function CancelDialog({
  open,
  onOpenChange,
  onConfirm,
  busy,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (reasonCode: CancelReasonCode) => void
  busy?: boolean
}) {
  const [reason, setReason] = useState<CancelReasonCode | null>(null)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Cancel escalation</DialogTitle>
        </DialogHeader>

        <RadioGroup
          value={reason ?? undefined}
          onValueChange={(v) => setReason(v as CancelReasonCode)}
        >
          {CANCEL_REASON_CODES.map((code) => (
            <div key={code} className="flex items-center gap-2">
              <RadioGroupItem value={code} id={`cancel-${code}`} />
              <Label htmlFor={`cancel-${code}`}>{CANCEL_LABELS[code]}</Label>
            </div>
          ))}
        </RadioGroup>

        <DialogFooter>
          <Button variant="neutral" onClick={() => onOpenChange(false)}>
            Keep open
          </Button>
          <Button
            variant="destructive"
            aria-disabled={reason === null || busy}
            title={reason === null ? 'Choose a reason first.' : undefined}
            onClick={() => {
              if (reason === null || busy) return
              onConfirm(reason)
            }}
          >
            Cancel escalation
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
