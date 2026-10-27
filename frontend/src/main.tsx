import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { WindowManagerProvider } from './components/WindowManager'
import './index.css'

const qc = new QueryClient()
createRoot(document.getElementById('root')!).render(
  <StrictMode><QueryClientProvider client={qc}><WindowManagerProvider><App /></WindowManagerProvider></QueryClientProvider></StrictMode>,
)
