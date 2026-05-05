import urllib.request
import os

urls = {
    "1_dd5837b116d0462d8f880ac56476f817.html": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sXzIzNzI3ZTZkNmVlNDQ4ODZiYjNiZGEzMzQxOGZkZmViEgsSBxDzptqk7QoYAZIBJAoKcHJvamVjdF9pZBIWQhQxMTAyMjQ3NTEzMDA4MDc5NjQ5NQ&filename=&opi=89354086",
    "2_03286486c8954a29b2593d3c7ea66302.html": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sX2E0YWQzNzY2MzUwNzQ3YzJhZjI2NGRjMTNmMjRiMTlkEgsSBxDzptqk7QoYAZIBJAoKcHJvamVjdF9pZBIWQhQxMTAyMjQ3NTEzMDA4MDc5NjQ5NQ&filename=&opi=89354086",
    "3_4efcc4c46de14702b4cbf4619c1ba401.html": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sXzA4Y2E2ZGRhMzdmNTQwODQ4N2Q3NDExMjBhMDc2MWU3EgsSBxDzptqk7QoYAZIBJAoKcHJvamVjdF9pZBIWQhQxMTAyMjQ3NTEzMDA4MDc5NjQ5NQ&filename=&opi=89354086",
    "4_64e0b5f8c9684f0d90e192a3eb21d1ee.html": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sXzQyMzJlMTZkM2Y5YTQ3YjY5MjQ1NTNmOGZiNzQwMWZhEgsSBxDzptqk7QoYAZIBJAoKcHJvamVjdF9pZBIWQhQxMTAyMjQ3NTEzMDA4MDc5NjQ5NQ&filename=&opi=89354086",
    "5_ec2fd10a7d2c4c1185fdeb23e0927263.html": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sXzEyYTQ4MGY2ZGI3MDQyNDI4MGQ5OTQwYTM0NmUwNzAyEgsSBxDzptqk7QoYAZIBJAoKcHJvamVjdF9pZBIWQhQxMTAyMjQ3NTEzMDA4MDc5NjQ5NQ&filename=&opi=89354086",
    "6_ecdfd1d04d7c482a886c43a45f194deb.html": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sXzA2ZDMxNjM3NTAyNDQ5MDk4ZGZkODk5MTBiZTU5OTMzEgsSBxDzptqk7QoYAZIBJAoKcHJvamVjdF9pZBIWQhQxMTAyMjQ3NTEzMDA4MDc5NjQ5NQ&filename=&opi=89354086",
    "7_2b942fdbecac4908b7ae8acbcf741b8e.html": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sXzM3YWZkZWJmZjIzZTRjMGU5YTYyZGIzNWEyZTcwYTZkEgsSBxDzptqk7QoYAZIBJAoKcHJvamVjdF9pZBIWQhQxMTAyMjQ3NTEzMDA4MDc5NjQ5NQ&filename=&opi=89354086",
    "8_3fe76cd7e6284b829b20bb5e93cd18ea.html": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sX2Q0YWJhODA1ZGVlODRhNWVhNDU0YjcwM2YzZDFkMmRkEgsSBxDzptqk7QoYAZIBJAoKcHJvamVjdF9pZBIWQhQxMTAyMjQ3NTEzMDA4MDc5NjQ5NQ&filename=&opi=89354086",
    "9_b8f716e25fd54dcaa73ec4ab00555341.html": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sXzg4NDJiNDQ0OWFhNzRhOTBhNjliZjM3ODkyZTE0M2QyEgsSBxDzptqk7QoYAZIBJAoKcHJvamVjdF9pZBIWQhQxMTAyMjQ3NTEzMDA4MDc5NjQ5NQ&filename=&opi=89354086"
}

os.makedirs("scratch/screens", exist_ok=True)

for filename, url in urls.items():
    print(f"Downloading {filename}...")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            with open(f"scratch/screens/{filename}", 'wb') as f:
                f.write(response.read())
        print(f"Success: {filename}")
    except Exception as e:
        print(f"Failed to download {filename}: {e}")
