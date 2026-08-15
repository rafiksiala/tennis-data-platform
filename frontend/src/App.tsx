import { Route, Routes } from 'react-router-dom'
import { CalendarPage } from './pages/CalendarPage'
import { MatchDetailPage } from './pages/MatchDetailPage'

function App() {
  return (
    <div className="min-h-screen bg-slate-50">
      <Routes>
        <Route path="/" element={<CalendarPage />} />
        <Route path="/matches/:id" element={<MatchDetailPage />} />
      </Routes>
    </div>
  )
}

export default App
