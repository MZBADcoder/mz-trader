import { AppProvider } from './providers'
import { AppRouter } from './routes'
import './styles/global.css'

export function App() {
  return (
    <AppProvider>
      <AppRouter />
    </AppProvider>
  )
}

