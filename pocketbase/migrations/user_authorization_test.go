package migrations

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/pocketbase/pocketbase/apis"
	"github.com/pocketbase/pocketbase/core"
)

func TestUserAuthorizedRecordAPI(t *testing.T) {
	app := core.NewBaseApp(core.BaseAppConfig{DataDir: t.TempDir()})
	if err := app.Bootstrap(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { app.ResetBootstrapState() })
	if err := app.RunAllMigrations(); err != nil {
		t.Fatal(err)
	}
	app.Settings().Logs.MaxDays = 0
	router, err := apis.NewRouter(app)
	if err != nil {
		t.Fatal(err)
	}
	mux, err := router.BuildMux()
	if err != nil {
		t.Fatal(err)
	}
	call := func(method, path, token string, body map[string]any, status int) map[string]any {
		t.Helper()
		encoded, err := json.Marshal(body)
		if err != nil {
			t.Fatal(err)
		}
		request := httptest.NewRequest(method, path, bytes.NewReader(encoded))
		request.Header.Set("Content-Type", "application/json")
		if token != "" {
			request.Header.Set("Authorization", token)
		}
		response := httptest.NewRecorder()
		mux.ServeHTTP(response, request)
		if response.Code != status {
			t.Fatalf("%s %s: expected %d, got %d", method, path, status, response.Code)
		}
		var result map[string]any
		if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
			t.Fatal(err)
		}
		return result
	}
	register := func(email string) (string, string) {
		t.Helper()
		user := call(http.MethodPost, "/api/collections/users/records", "", map[string]any{
			"email": email, "password": "password123", "passwordConfirm": "password123",
		}, 200)
		login := call(http.MethodPost, "/api/collections/users/auth-with-password", "", map[string]any{
			"identity": email, "password": "password123",
		}, 200)
		refresh := call(http.MethodPost, "/api/collections/users/auth-refresh", login["token"].(string), nil, 200)
		return user["id"].(string), refresh["token"].(string)
	}
	firstID, firstToken := register("first@example.com")
	secondID, secondToken := register("second@example.com")
	for _, forbidden := range []string{"verified", "emailVisibility", "id"} {
		call(http.MethodPost, "/api/collections/users/records", "", map[string]any{
			"email": forbidden + "@example.com", "password": "password123", "passwordConfirm": "password123", forbidden: true,
		}, 400)
	}
	// Hidden tokenKey input is stripped by PocketBase before rule evaluation.
	user := call(http.MethodPost, "/api/collections/users/records", "", map[string]any{
		"email": "hidden@example.com", "password": "password123", "passwordConfirm": "password123", "tokenKey": "chosen-key",
	}, 200)
	storedUser, err := app.FindRecordById("users", user["id"].(string))
	if err != nil || storedUser.GetString("tokenKey") == "chosen-key" {
		t.Fatal("anonymous registration must not control the hidden token key")
	}
	data := map[string]any{
		"analysis_id": "01234567-89ab-4cde-8fab-0123456789ab", "created_by": firstID,
		"original_text": "Event", "status": "Processing", "embedding_status": "Processing",
	}
	path := "/api/collections/Analysis/records"
	call(http.MethodPost, path, "", data, 400)
	call(http.MethodPost, path, secondToken, data, 400)
	created := call(http.MethodPost, path, firstToken, data, 200)
	itemPath := path + "/" + created["id"].(string)
	call(http.MethodGet, itemPath, firstToken, nil, 404)
	call(http.MethodPatch, itemPath, firstToken, map[string]any{
		"title": "Title", "predictions": map[string]any{"risks": []any{}},
		"status": "Complete", "embedding_status": "Complete", "created_by": firstID,
		"analysis_id": data["analysis_id"], "original_text": "Event",
	}, 200)
	call(http.MethodPatch, itemPath, secondToken, map[string]any{"status": "Failed"}, 404)
	call(http.MethodPatch, itemPath, firstToken, map[string]any{"created_by": secondID}, 404)
	call(http.MethodPatch, itemPath, firstToken, map[string]any{"original_text": "Replacement"}, 404)
	call(http.MethodPatch, itemPath, firstToken, map[string]any{"analysis_id": "11234567-89ab-4cde-8fab-0123456789ab"}, 404)
	call(http.MethodGet, itemPath, firstToken, nil, 200)
	call(http.MethodGet, itemPath, secondToken, nil, 404)
	call(http.MethodGet, itemPath, "", nil, 404)
	listed := call(http.MethodGet, path, firstToken, nil, 200)
	if len(listed["items"].([]any)) != 1 {
		t.Fatal("owner should see their completed analysis")
	}
	for _, token := range []string{secondToken, ""} {
		listed := call(http.MethodGet, path, token, nil, 200)
		if len(listed["items"].([]any)) != 0 {
			t.Fatal("history must not expose another user's analyses")
		}
	}
	call(http.MethodDelete, itemPath, firstToken, nil, 403)
	call(http.MethodGet, "/api/collections/users/records", firstToken, nil, 403)

	// Legacy unattributed analyses stay inaccessible to ordinary user writes.
	collection, err := app.FindCollectionByNameOrId("Analysis")
	if err != nil {
		t.Fatal(err)
	}
	legacy := core.NewRecord(collection)
	legacy.Set("analysis_id", "21234567-89ab-4cde-8fab-0123456789ab")
	legacy.Set("original_text", "Legacy event")
	legacy.Set("status", "Complete")
	legacy.Set("embedding_status", "Complete")
	if err := app.Save(legacy); err != nil {
		t.Fatal(err)
	}
	call(http.MethodPatch, path+"/"+legacy.Id, firstToken, map[string]any{"created_by": firstID}, 404)
	call(http.MethodGet, path+"/"+legacy.Id, firstToken, nil, 404)
	for _, status := range []string{"Processing", "Failed"} {
		call(http.MethodPatch, itemPath, firstToken, map[string]any{"status": status}, 200)
		call(http.MethodGet, itemPath, firstToken, nil, 404)
		listed := call(http.MethodGet, path, firstToken, nil, 200)
		if len(listed["items"].([]any)) != 0 {
			t.Fatal("only complete, attributed analyses belong in history")
		}
	}
}
