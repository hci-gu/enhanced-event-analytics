package migrations

import (
	"testing"

	"github.com/pocketbase/pocketbase/core"
)

func TestLocationMigrationAndRoundTrip(t *testing.T) {
	app := core.NewBaseApp(core.BaseAppConfig{DataDir: t.TempDir()})
	if err := app.Bootstrap(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { app.ResetBootstrapState() })
	if err := app.RunAllMigrations(); err != nil {
		t.Fatal(err)
	}
	collection, err := app.FindCollectionByNameOrId("Analysis")
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"location", "location_error"} {
		field, ok := collection.Fields.GetByName(name).(*core.JSONField)
		if !ok || field.Required {
			t.Fatalf("%s must be optional JSON", name)
		}
	}
	record := core.NewRecord(collection)
	record.Set("analysis_id", "01234567-89ab-4cde-8fab-0123456789ab")
	record.Set("original_text", "Stockholm")
	record.Set("status", "Complete")
	record.Set("embedding_status", "Complete")
	record.Set("location", []any{map[string]any{
		"longitude": 18.06, "latitude": 59.33, "roles": []string{"event-site"},
	}})
	record.Set("location_error", map[string]any{"code": 206, "message": "Limited"})
	if err := app.Save(record); err != nil {
		t.Fatal(err)
	}
	stored, err := app.FindRecordById(collection.Id, record.Id)
	if err != nil {
		t.Fatal(err)
	}
	var places []map[string]any
	var failure map[string]any
	if err := stored.UnmarshalJSONField("location", &places); err != nil {
		t.Fatal(err)
	}
	if err := stored.UnmarshalJSONField("location_error", &failure); err != nil {
		t.Fatal(err)
	}
	if len(places) != 1 || places[0]["longitude"] != 18.06 || failure["code"] != float64(206) {
		t.Fatal("location and warning must survive JSON round trip")
	}
	if err := removeLocationFields(app); err != nil {
		t.Fatal(err)
	}
	collection, _ = app.FindCollectionByNameOrId("Analysis")
	if collection.Fields.GetByName("location") != nil || collection.Fields.GetByName("location_error") != nil {
		t.Fatal("rollback must remove location fields")
	}
	if _, err := app.FindRecordById(collection.Id, record.Id); err != nil {
		t.Fatal("rollback must preserve analysis records")
	}
	if err := addLocationFields(app); err != nil {
		t.Fatal(err)
	}
}
