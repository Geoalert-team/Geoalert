const api = axios.create({
  baseURL: process.env.REACT_APP_API_URL || "http://127.0.0.1:8000",
  withCredentials: true, // <-- required for session cookies to be sent/received
});
