import { Navigate, Route, Routes } from 'react-router-dom'
import { LoginForm } from './features/auth/LoginForm'
import { DispatchHome } from './features/dispatch/DispatchHome'
import { DriverHome } from './features/driver/DriverHome'
import { OpsHome } from './features/operator/OpsHomes'
import './App.css'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/driver/login" replace />} />
      <Route
        path="/driver/login"
        element={
          <LoginForm
            portal="driver"
            title="Driver sign-in"
            subtitle="Access your shipment, ETA, and appointment context."
          />
        }
      />
      <Route
        path="/ops/login"
        element={
          <LoginForm
            portal="ops"
            title="Ops sign-in"
            subtitle="Operator (facility) or Admin (global read-only) — same dashboard, scope from JWT."
          />
        }
      />
      {/* Legacy three-portal aliases — keep wrong-bookmark safe */}
      <Route path="/operator/login" element={<Navigate to="/ops/login" replace />} />
      <Route path="/admin/login" element={<Navigate to="/ops/login" replace />} />
      <Route path="/operator" element={<Navigate to="/ops" replace />} />
      <Route path="/admin" element={<Navigate to="/ops" replace />} />
      <Route path="/driver" element={<DriverHome />} />
      <Route path="/ops" element={<OpsHome />} />
      <Route path="/dispatch" element={<DispatchHome />} />
      <Route path="*" element={<Navigate to="/driver/login" replace />} />
    </Routes>
  )
}
