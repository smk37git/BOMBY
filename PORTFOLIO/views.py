from django.shortcuts import render
from django.http import JsonResponse
import requests
import json

def portfolio(request):
    return render(request, 'PORTFOLIO/portfolio.html')

def bomby_project(request):
    return render(request, 'PORTFOLIO/bomby_project.html')\

def github_latest_commit(request, username, repo):
    api_url = f"https://api.github.com/repos/{username}/{repo}/commits"
    print(f"Requesting: {api_url}")
    
    try:
        response = requests.get(api_url)
        print(f"Status code: {response.status_code}")
        print(f"Response content: {response.text[:100]}...")  # Print first 100 chars
        
        response.raise_for_status()
        commits = response.json()
        return JsonResponse(commits[0] if commits else {})
    except requests.exceptions.RequestException as e:
        print(f"Request error: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {str(e)}")
        return JsonResponse({"error": "Invalid JSON response"}, status=500)
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)
