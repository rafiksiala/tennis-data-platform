import { Route, Routes } from 'react-router-dom'
import { CalendarPage } from './pages/CalendarPage'
import { MatchDetailPage } from './pages/MatchDetailPage'
import { PlayerPage } from './pages/PlayerPage'

function App() {
  return (
    <div className="min-h-screen bg-slate-50">
      <Routes>
        <Route path="/" element={<CalendarPage />} />
        <Route path="/matches/:id" element={<MatchDetailPage />} />
        <Route path="/players/:id" element={<PlayerPage />} />
      </Routes>
    </div>
  )
}

export default App
