from rest_framework.throttling import SimpleRateThrottle

class EstimatePriceThrottle(SimpleRateThrottle):
    scope = 'estimate_price'

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }

class AuthThrottle(SimpleRateThrottle):
    scope = 'auth_limit'

    def get_cache_key(self, request, view):
        # We can throttle by IP address (ident)
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request)
        }
