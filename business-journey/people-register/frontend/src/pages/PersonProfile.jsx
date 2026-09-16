import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { getPerson } from '../api.js';

export default function PersonProfile() {
    const { personId } = useParams();
    const [person, setPerson] = useState(null);

    useEffect(() => {
        getPerson(personId).then(setPerson);
    }, [personId]);

    if (!person) return <p>Loading...</p>;

    return (
        <div>
            <h1>{person.name}</h1>
            {person.risk_flags.includes('linked_to_insolvent_company') && (
                <p role="alert">Linked to an insolvent company</p>
            )}
            <h2>Roles</h2>
            <ul>
                {person.roles.map((r, i) => (
                    <li key={i}>
                        {r.role_type} at {r.company} ({r.started_at} - {r.ended_at ?? 'present'})
                    </li>
                ))}
            </ul>
        </div>
    );
}
