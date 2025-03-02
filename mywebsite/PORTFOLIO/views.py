from django.shortcuts import render

def portfolio(request):
    return render(request, 'PORTFOLIO/portfolio.html')

def bomby_project(request):
    return render(request, 'PORTFOLIO/bomby_project.html')