from tests.helpers import import_case


def test_create_and_list_case(client, tmp_path):
    created = import_case(client, tmp_path, name="Demo Stroke Case")
    case_id = created["id"]

    listed = client.get("/api/cases")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [case_id]
    assert listed.json()[0]["ready_for_inference"] is True


def test_missing_case_uses_stable_error_shape(client):
    response = client.get("/api/cases/not-a-real-case")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "case_not_found", "message": "Case not found"}
    }
