from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json


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