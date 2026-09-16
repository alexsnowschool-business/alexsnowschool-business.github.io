import { useState } from 'react';
import { Link } from 'react-router-dom';
import { search } from '../api.js';

export default function Search() {
    const [query, setQuery] = useState('');
    const [results, setResults] = useState(null);

    async function handleSearch(event) {
        event.preventDefault();
        setResults(await search(query));
    }

    return (
        <div>
            <h1>Search</h1>
            <form onSubmit={handleSearch}>
                <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Name..." />
                <button type="submit">Search</button>
            </form>

            {results && (
                <div>
                    <h2>People</h2>
                    <ul>
                        {results.people.map((p) => (
                            <li key={p.id}>
                                <Link to={`/people/${p.id}`}>{p.name}</Link>
                            </li>
                        ))}
                    </ul>

                    <h2>Companies</h2>
                    <ul>
                        {results.companies.map((c) => (
                            <li key={c.id}>{c.name}</li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}
