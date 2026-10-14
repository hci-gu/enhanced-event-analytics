import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './colors.css'
import './index.css'
import AuthGate from './AuthGate.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthGate />
  </StrictMode>,
)
