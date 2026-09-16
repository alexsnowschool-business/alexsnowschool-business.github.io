import { Routes, Route, Link } from 'react-router-dom';
import Search from './pages/Search.jsx';
import PersonProfile from './pages/PersonProfile.jsx';
import RiskDashboard from './pages/RiskDashboard.jsx';

export default function App() {
    return (
        <div>
            <nav>
                <Link to="/">Search</Link> | <Link to="/risk">Risk Dashboard</Link>
            </nav>
            <Routes>
                <Route path="/" element={<Search />} />
                <Route path="/people/:personId" element={<PersonProfile />} />
                <Route path="/risk" element={<RiskDashboard />} />
            </Routes>
        </div>
    );
}
