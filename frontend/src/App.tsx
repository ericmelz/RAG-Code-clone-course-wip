import { useMemo } from 'react'
import Router from 'routes/router'
import { BrowserRouter } from "react-router"
import { Box, ThemeProvider, CssBaseline, createTheme, useMediaQuery } from '@mui/material'
import NavigationTabs from 'components/NavigationTabs'

function App() {
  const prefersDarkMode = useMediaQuery('(prefers-color-scheme: dark)')

  const theme = useMemo(
    () => createTheme({ palette: { mode: prefersDarkMode ? 'dark' : 'light' } }),
    [prefersDarkMode],
  )

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <Box sx={{ width: '100vw', minHeight: '100vh' }}>
          <NavigationTabs />
          <Router />
        </Box>
      </BrowserRouter>
    </ThemeProvider>
  )
}

export default App
