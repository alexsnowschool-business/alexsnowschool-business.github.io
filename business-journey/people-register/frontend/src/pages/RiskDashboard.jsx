import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getRiskDashboard } from '../api.js';

export default function RiskDashboard() {
    const [people, setPeople] = useState(null);

    useEffect(() => {
        getRiskDashboard().then((data) => setPeople(data.people));
    }, []);

    if (!people) return <p>Loading...</p>;

    return (
        <div>
            <h1>Risk Dashboard</h1>
            <p>People currently linked to an insolvent company:</p>
            <ul>
                {people.map((p) => (
                    <li key={p.id}>
                        <Link to={`/people/${p.id}`}>{p.name}</Link> — {p.company}
                    </li>
                ))}
            </ul>
        </div>
    );
}
