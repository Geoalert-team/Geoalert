import { apiBase } from './axiosClient';

describe('apiBase', () => {
  it('uses the site’s own address in a production build', () => {
    expect(apiBase({ NODE_ENV: 'production' })).toBe('');
  });

  it('uses runserver in development and tests', () => {
    expect(apiBase({ NODE_ENV: 'development' })).toBe('http://localhost:8000');
    expect(apiBase({ NODE_ENV: 'test' })).toBe('http://localhost:8000');
  });

  it('lets REACT_APP_API_URL override both', () => {
    const env = { NODE_ENV: 'production', REACT_APP_API_URL: 'https://geoalert.example.org' };
    expect(apiBase(env)).toBe('https://geoalert.example.org');
  });

  it('drops a pasted line break, spaces and trailing slashes', () => {
    const env = { NODE_ENV: 'production', REACT_APP_API_URL: ' https://geoalert.example.org/\n' };
    expect(apiBase(env)).toBe('https://geoalert.example.org');
  });

  it('treats a blank REACT_APP_API_URL as unset', () => {
    expect(apiBase({ NODE_ENV: 'production', REACT_APP_API_URL: '  ' })).toBe('');
  });
});
