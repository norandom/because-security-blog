# API Migration Guide

## Migrating to API v1

Starting from version 2.1.0, all API endpoints have been moved under the `/api/v1` prefix for better versioning support. Legacy endpoints without the prefix are deprecated and will be removed in version 3.0.0.

### Endpoint Changes

All endpoints now require the `/api/v1` prefix:

| Old Endpoint | New Endpoint |
|--------------|--------------|
| `/posts` | `/api/v1/posts` |
| `/posts/all-tenants` | `/api/v1/posts/all-tenants` |
| `/posts/{slug}` | `/api/v1/posts/{slug}` |
| `/posts/{slug}/related` | `/api/v1/posts/{slug}/related` |
| `/search` | `/api/v1/search` |
| `/search/suggest` | `/api/v1/search/suggest` |
| `/stats` | `/api/v1/stats` |
| `/tenants` | `/api/v1/tenants` |
| `/tenants/{tenant}` | `/api/v1/tenants/{tenant}` |
| `/tenants/{tenant}/posts` | `/api/v1/tenants/{tenant}/posts` |
| `/health` | `/api/v1/health` |
| `/metrics` | `/api/v1/metrics` |
| `/attachments/{slug}/{path}` | `/api/v1/attachments/{slug}/{path}` |

### Documentation URLs

- OpenAPI JSON: `/api/v1/openapi.json`
- Swagger UI: `/api/v1/docs`
- ReDoc: `/api/v1/redoc`

### Security Enhancements

1. **Input Sanitization**: All user inputs are now sanitized to prevent injection attacks
2. **Security Headers**: Added comprehensive security headers (X-Frame-Options, CSP, etc.)
3. **Rate Limiting**: Stricter rate limits for legacy endpoints
4. **Cache Headers**: Proper cache control headers for CDN optimization

### Migration Steps

1. Update your API client to use the new `/api/v1` prefix for all endpoints
2. Update any hardcoded URLs in your frontend application
3. Test all functionality with the new endpoints
4. Monitor deprecation warnings in response headers

### Deprecation Timeline

- **December 2024**: Legacy endpoints deprecated (return 301 redirects)
- **January 2025**: Legacy endpoints removed completely

### Response Format

The API response format remains unchanged. Only the endpoint URLs have been updated.

### Example Migration

**Before:**
```javascript
const response = await fetch('https://api.example.com/posts');
```

**After:**
```javascript
const response = await fetch('https://api.example.com/api/v1/posts');
```

### Need Help?

If you encounter any issues during migration, please open an issue on GitHub: https://github.com/norandom/because-security-blog/issues