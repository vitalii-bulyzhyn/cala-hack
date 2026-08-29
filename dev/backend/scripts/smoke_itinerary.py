import json
import os
import time
import urllib.error
import urllib.request
from uuid import uuid4

API_ROOT = "http://127.0.0.1:8000/api/v1"


def request_json(request: urllib.request.Request) -> tuple[int, dict, dict[str, str]]:
    try:
        response = urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as error:
        return (
            error.code,
            json.load(error),
            {key.lower(): value for key, value in error.headers.items()},
        )
    with response:
        body = response.read()
        return (
            response.status,
            json.loads(body) if body else {},
            {key.lower(): value for key, value in response.headers.items()},
        )


idempotency_key = f"smoke-{uuid4()}"


def create_request(city: str, tags: list[str]) -> urllib.request.Request:
    return urllib.request.Request(
        f"{API_ROOT}/itineraries",
        data=json.dumps({"city": city, "tags": tags}).encode(),
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        },
        method="POST",
    )


city = "Barcelona"
tags = ["architecture", "art", "local food"]
create_status, accepted, create_headers = request_json(create_request(city, tags))
assert create_status == 202, accepted
assert accepted["status"] == "pending", accepted
assert create_headers["location"] == accepted["status_url"]

replay_status, replayed, replay_headers = request_json(
    create_request(f"  {city}  ", ["local food", "ART", "architecture"])
)
assert replay_status == 202, replayed
assert replayed["id"] == accepted["id"]
assert replayed["status_url"] == accepted["status_url"]
assert replayed["status"] in {"pending", "done", "fail"}
assert replay_headers["idempotency-replayed"] == "true"

conflict_status, conflict, _ = request_json(create_request("Valencia", tags))
assert conflict_status == 409, conflict
assert conflict["error"]["code"] == "IDEMPOTENCY_KEY_REUSED", conflict

get_request = urllib.request.Request(f"{API_ROOT}/itineraries/{accepted['id']}")
get_status, resource, _ = request_json(get_request)
assert get_status == 200, resource
assert resource["city"] == city, resource
assert resource["tags"] == tags, resource
assert resource["status"] == "pending", resource
assert resource["stage"] == "learning_preferences", resource
assert resource["result"] is None and resource["error"] is None, resource

for page_position in range(1, 4):
    next_page_request = urllib.request.Request(
        f"{API_ROOT}/itineraries/{accepted['id']}/preference-pages/next"
    )
    next_status, page, _ = request_json(next_page_request)
    assert next_status == 200, page
    assert page["position"] == page_position, page
    assert page["layout"] == "pair", page
    assert len(page["entries"]) == 2, page
    decisions = {}
    for index, entry in enumerate(page["entries"]):
        assert set(entry) == {
            "id",
            "name",
            "category",
            "description",
            "image_link",
            "decision",
        }
        assert entry["decision"] is None
        decisions[entry["id"]] = "like" if index == 0 else "dislike"
    feedback_request = urllib.request.Request(
        f"{API_ROOT}/itineraries/{accepted['id']}/preference-pages/{page['id']}/feedback",
        data=json.dumps({"decisions": decisions}).encode(),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    feedback_status, recorded, _ = request_json(feedback_request)
    assert feedback_status == 200, recorded

adaptive_status, adaptive_page, _ = request_json(next_page_request)
assert adaptive_status == 200, adaptive_page
assert adaptive_page["position"] == 4, adaptive_page
assert adaptive_page["source"] == "adaptive", adaptive_page
assert adaptive_page["layout"] in {"single", "pair"}, adaptive_page
assert len(adaptive_page["entries"]) in {1, 2}, adaptive_page
adaptive_decisions = {
    entry["id"]: "like" if index == 0 else "dislike"
    for index, entry in enumerate(adaptive_page["entries"])
}
adaptive_feedback_request = urllib.request.Request(
    f"{API_ROOT}/itineraries/{accepted['id']}/preference-pages/{adaptive_page['id']}/feedback",
    data=json.dumps({"decisions": adaptive_decisions}).encode(),
    headers={"Content-Type": "application/json"},
    method="PUT",
)
adaptive_feedback_status, recorded, _ = request_json(adaptive_feedback_request)
assert adaptive_feedback_status == 200, recorded

no_more_status, no_more_page, _ = request_json(next_page_request)
assert no_more_status == 204, no_more_page

complete_request = urllib.request.Request(
    f"{API_ROOT}/itineraries/{accepted['id']}/preference-learning/complete",
    data=b"",
    method="POST",
)
complete_status, completed, _ = request_json(complete_request)
assert complete_status == 202, completed
assert completed["id"] == accepted["id"], completed

for _ in range(240):
    get_status, resource, _ = request_json(get_request)
    assert get_status == 200, resource
    if resource["status"] in {"done", "fail"}:
        break
    time.sleep(1)

assert resource["status"] in {"done", "fail"}, resource
offline_demo_expected = os.getenv("OFFLINE_DEMO_ENABLED", "true").lower() not in {
    "0",
    "false",
    "no",
    "off",
} and any(not os.getenv(key, "").strip() for key in ("OPENAI_API_KEY", "CALA_API_KEY", "FAL_KEY"))
if offline_demo_expected:
    assert resource["status"] == "done", resource
if resource["status"] == "done":
    result = resource["result"]
    assert "/media/" in result["journal_image"]["url"], result
    assert len(result["places"]) >= 3, result
    assert all(place["links"] for place in result["places"]), result
else:
    assert resource["result"] is None, resource
    assert resource["error"]["code"] != "CONTENT_PIPELINE_NOT_IMPLEMENTED", resource

print(f"Itinerary/preference/worker lifecycle passed for {accepted['id']}")
