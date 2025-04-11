from django.shortcuts import render
from django.http import JsonResponse
import requests
import json

from STORE.models import Review

def portfolio(request):
    return render(request, 'PORTFOLIO/portfolio.html')

def bomby_project(request):
    return render(request, 'PORTFOLIO/bomby_project.html')

def github_latest_bomby_commit(request, username, repo):
    api_url = f"https://api.github.com/repos/{username}/{repo}/commits"
    
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        commits = response.json()
        
        if commits:
            commit = commits[0]
            # Get stats for this commit
            commit_url = commit['url']
            stats_response = requests.get(commit_url)
            stats_response.raise_for_status()
            commit_details = stats_response.json()
            
            # Combine the data
            commit['stats'] = commit_details.get('stats', {})
            
            return JsonResponse(commit)
        return JsonResponse({})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def fraternity_project(request):
    return render(request, 'PORTFOLIO/fraternity_project.html')

def github_latest_fraternity_commit(request, username, repo):
    api_url = f"https://api.github.com/repos/{username}/{repo}/commits"
    
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        commits = response.json()
        
        if commits:
            commit = commits[0]
            # Get stats for this commit
            commit_url = commit['url']
            stats_response = requests.get(commit_url)
            stats_response.raise_for_status()
            commit_details = stats_response.json()
            
            # Combine the data
            commit['stats'] = commit_details.get('stats', {})
            
            return JsonResponse(commit)
        return JsonResponse({})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def github_project(request):
    return render(request, 'PORTFOLIO/github_project.html')

def college_project(request):
    return render(request, 'PORTFOLIO/college_project.html')

def steam_workshop(request):
    return render(request, 'PORTFOLIO/steam_workshop.html')

def get_all_reviews():
    """Helper function to get all reviews across products"""
    return Review.objects.all().select_related('order__user', 'order__product')

def stream_setup(request):
    product_reviews = get_all_reviews()
    return render(request, 'PORTFOLIO/stream_setup.html', {'product_reviews': product_reviews})