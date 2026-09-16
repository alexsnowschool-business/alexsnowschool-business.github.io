const BASE_URL = import.meta.env.VITE_API_BASE_URL;
const API_KEY = import.meta.env.VITE_API_KEY;

async function request(path) {
    const response = await fetch(`${BASE_URL}${path}`, {
        headers: { apikey: API_KEY },
    });
    if (!response.ok) {
        throw new Error(`Request to ${path} failed: ${response.status}`);
    }
    return response.json();
}

export function search(query) {
    return request(`/search?q=${encodeURIComponent(query)}`);
}

export function getPerson(personId) {
    return request(`/people/${personId}`);
}

export function getCompany(companyId) {
    return request(`/companies/${companyId}`);
}

export function getRiskDashboard() {
    return request('/risk');
}
