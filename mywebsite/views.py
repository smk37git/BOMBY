from django.http import HttpResponse

def health_check(request):
    try:
        from django.db import connection
        connection.ensure_connection()
        return HttpResponse("Database OK")
    except Exception as e:
        return HttpResponse(f"Error: {str(e)}", status=500)