from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

def home(request):
    return render(request, 'home.html')


def login_view(request):
    if request.method == "POST":
        login_input = request.POST.get("email")
        password = request.POST.get("password")

        username = login_input

        try:
            user_obj = User.objects.get(email=login_input)
            username = user_obj.username
        except User.DoesNotExist:
            pass

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect("huddle")

        return render(request, "login.html", {
            "error": "Invalid email or password"
        })

    return render(request, "login.html")


def register_view(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("huddle")

        return render(request, "register.html", {
            "form": form
        })

    form = UserCreationForm()
    return render(request, "register.html", {
        "form": form
    })


@login_required(login_url="login")
def huddle_view(request):
    return render(request, "huddle.html")


@login_required(login_url="login")
def timeline_view(request):
    return render(request, "timeline.html")


@login_required(login_url="login")
def profile_view(request):
    return render(request, "profile.html")

@csrf_exempt
def parse_text(request):
    if request.method == "POST":
        try:
            body = json.loads(request.body)

            # Mock parsed tasks
            data = [
                {"task": "Finish homework", "duration": 120, "priority": "high"},
                {"task": "Go to gym", "duration": 60, "priority": "medium"},
                {"task": "Meeting", "time": "15:00", "duration": 60}
            ]

            return JsonResponse({
                "success": True,
                "data": data,
                "error": None
            })

        except Exception as e:
            return JsonResponse({
                "success": False,
                "data": None,
                "error": str(e)
            })

    return JsonResponse({"success": False, "error": "Only POST allowed"})


@csrf_exempt
def upload_image(request):
    if request.method == "POST":
        # Mock OCR result
        extracted_text = "Finish project, meeting at 3pm, gym"

        return JsonResponse({
            "success": True,
            "data": {
                "text": extracted_text
            },
            "error": None
        })

    return JsonResponse({"success": False, "error": "Only POST allowed"})


@csrf_exempt
def generate_schedule(request):
    if request.method == "POST":
        try:
            # Mock schedule output
            schedule = [
                {"time": "09:00", "task": "Finish homework"},
                {"time": "11:00", "task": "Go to gym"},
                {"time": "15:00", "task": "Meeting"}
            ]

            return JsonResponse({
                "success": True,
                "data": schedule,
                "error": None
            })

        except Exception as e:
            return JsonResponse({
                "success": False,
                "data": None,
                "error": str(e)
            })

    return JsonResponse({"success": False, "error": "Only POST allowed"})