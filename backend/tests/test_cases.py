def test_create_and_list_case(client):
    created = client.post("/api/cases", json={"name": "Demo Stroke Case"})
    assert created.status_code == 201
    case_id = created.json()["id"]

    listed = client.get("/api/cases")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [case_id]
    assert listed.json()[0]["ready_for_inference"] is False


def test_missing_case_uses_stable_error_shape(client):
    response = client.get("/api/cases/not-a-real-case")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "case_not_found", "message": "Case not found"}
    }
