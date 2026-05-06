import { createBrowserRouter, RouterProvider } from 'react-router-dom'

import { AuthPage } from '@/pages/auth'
import { HomePage } from '@/pages/home'
import { NotFoundPage } from '@/pages/not-found'
import { TerminalPage } from '@/pages/terminal'

import { routePaths } from './route-paths'

const router = createBrowserRouter([
  {
    path: routePaths.home,
    element: <HomePage />,
  },
  {
    path: routePaths.auth,
    element: <AuthPage />,
  },
  {
    path: routePaths.terminal,
    element: <TerminalPage />,
  },
  {
    path: '*',
    element: <NotFoundPage />,
  },
])

export function AppRouter() {
  return <RouterProvider router={router} />
}

