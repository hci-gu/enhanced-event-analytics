package migrations

import (
	"testing"

	"github.com/pocketbase/pocketbase/core"
)

func TestAnalysisRecordConstraints(t *testing.T) {
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
	newRecord := func(uuid, status string) *core.Record {
		record := core.NewRecord(collection)
		record.Set("analysis_id", uuid)
		record.Set("status", status)
		record.Set("embedding_status", "Processing")
		record.Set("original_text", "  Original event text\nwith line breaks.  ")
		return record
	}
	for _, field := range []string{"original_text", "embedding_status"} {
		invalid := newRecord("11234567-89ab-4cde-8fab-0123456789ab", "Processing")
		invalid.Set(field, "")
		if err := app.Save(invalid); err == nil {
			t.Fatalf("missing %s was accepted", field)
		}
	}
	invalidEmbedding := newRecord("11234567-89ab-4cde-8fab-0123456789ab", "Processing")
	invalidEmbedding.Set("embedding_status", "Unknown")
	if err := app.Save(invalidEmbedding); err == nil {
		t.Fatal("invalid embedding status was accepted")
	}
	uuid := "01234567-89ab-4cde-8fab-0123456789ab"
	record := newRecord(uuid, "Processing")
	if err := app.Save(record); err != nil {
		t.Fatalf("processing record must allow missing title/results: %v", err)
	}
	if !record.GetDateTime("finished_at").IsZero() {
		t.Fatal("processing record must not have an automatic finish time")
	}
	for _, name := range []string{"dates", "dates_error"} {
		field, ok := collection.Fields.GetByName(name).(*core.JSONField)
		if !ok || field.Required {
			t.Fatalf("%s must be an optional JSON field for legacy records", name)
		}
	}
	if err := app.Save(newRecord(uuid, "Processing")); err == nil {
		t.Fatal("duplicate backend UUID was accepted")
	}
	for _, invalid := range []struct{ uuid, status string }{
		{"not-a-uuid", "Processing"},
		{"11234567-89ab-4cde-8fab-0123456789ab", "Unknown"},
		{"11234567-89ab-4cde-8fab-0123456789ab", ""},
	} {
		if err := app.Save(newRecord(invalid.uuid, invalid.status)); err == nil {
			t.Fatalf("invalid UUID/status accepted: %v", invalid)
		}
	}
	record.Set("predictions", map[string]any{"risks": []any{}})
	record.Set("dates", map[string]any{"published_at": "2026-10-13", "event_end": nil})
	record.Set("dates_error", map[string]any{"code": 502, "message": "Date extraction failed"})
	record.Set("error", map[string]any{"workflow_id": "reach", "code": 502, "message": "Failed"})
	record.Set("status", "Failed")
	record.Set("embedding_status", "Complete")
	record.Set("finished_at", "2026-10-13 14:30:00.000Z")
	if err := app.Save(record); err != nil {
		t.Fatal(err)
	}
	stored, err := app.FindRecordById(collection.Id, record.Id)
	if err != nil {
		t.Fatal(err)
	}
	var predictions map[string]any
	var dates, datesError map[string]any
	if err := stored.UnmarshalJSONField("dates", &dates); err != nil {
		t.Fatal(err)
	}
	if err := stored.UnmarshalJSONField("dates_error", &datesError); err != nil {
		t.Fatal(err)
	}
	if dates["published_at"] != "2026-10-13" || dates["event_end"] != nil || datesError["code"] != float64(502) {
		t.Fatal("date values and nonfatal errors must survive a JSON round trip")
	}
	if err := stored.UnmarshalJSONField("predictions", &predictions); err != nil {
		t.Fatal(err)
	}
	if _, ok := predictions["risks"]; !ok || stored.GetString("status") != "Failed" {
		t.Fatal("failed record did not retain its completed predictions")
	}
	if stored.GetDateTime("created").IsZero() || stored.GetDateTime("updated").IsZero() {
		t.Fatal("automatic timestamps are missing")
	}
	if stored.GetString("original_text") != record.GetString("original_text") || stored.GetDateTime("finished_at").IsZero() {
		t.Fatal("original text or finish time was not persisted")
	}
	if stored.GetString("embedding_status") != "Complete" {
		t.Fatal("category failure must allow successful embedding")
	}
	stored.Set("status", "Complete")
	stored.Set("embedding_status", "Failed")
	if err := app.Save(stored); err != nil {
		t.Fatalf("embedding failure must allow successful category analysis: %v", err)
	}
	if collection.ListRule == nil || collection.ViewRule == nil || collection.CreateRule == nil || collection.UpdateRule == nil || collection.DeleteRule != nil {
		t.Fatal("attributed user reads and writes should be enabled; deletion stays locked")
	}
}
