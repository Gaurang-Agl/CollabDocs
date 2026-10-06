import time


class RequestLoggingMiddleware:
    """
    Logs HTTP method, endpoint path, response status code,
    and elapsed request time in milliseconds.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()

        response = self.get_response(request)

        duration_ms = (time.time() - start_time) * 1000

        print(
            f"[{request.method}] {request.path} "
            f"-> {response.status_code} "
            f"({duration_ms:.2f}ms)"
        )

        return response