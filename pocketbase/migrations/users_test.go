package migrations

import (
	"strings"
	"testing"

	"github.com/pocketbase/pocketbase/core"
)

func TestUserAuthenticationAndAnalysisCreators(t *testing.T) {
	app := core.NewBaseApp(core.BaseAppConfig{DataDir: t.TempDir()})
	if err := app.Bootstrap(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { app.ResetBootstrapState() })
	if err := app.RunAllMigrations(); err != nil {
		t.Fatal(err)
	}
	users, err := app.FindCollectionByNameOrId("users")
	if err != nil {
		t.Fatal(err)
	}
	if !users.IsAuth() || !users.PasswordAuth.Enabled || users.AuthToken.Duration != 604800 || users.AuthRule == nil || *users.AuthRule != "" {
		t.Fatal("email/password authentication without verification and seven-day tokens must be enabled")
	}
	if !users.Fields.GetByName("email").(*core.EmailField).Required || users.Fields.GetByName("password").(*core.PasswordField).Min != 8 {
		t.Fatal("required email and minimum password length are missing")
	}
	if users.CreateRule != nil || users.ListRule != nil || users.ViewRule != nil || users.UpdateRule != nil || users.DeleteRule != nil {
		t.Fatal("user record API must remain locked")
	}
	createUser := func(email string) *core.Record {
		user := core.NewRecord(users)
		user.SetEmail(email)
		user.SetPassword("password123")
		if err := app.Save(user); err != nil {
			t.Fatal(err)
		}
		if !user.ValidatePassword("password123") {
			t.Fatal("created user cannot authenticate with its password")
		}
		return user
	}
	first := createUser("first@example.com")
	second := createUser("second@example.com")
	duplicate := core.NewRecord(users)
	duplicate.SetEmail("first@example.com")
	duplicate.SetPassword("password123")
	if err := app.Save(duplicate); err == nil {
		t.Fatal("duplicate email must be rejected")
	}
	analysis, err := app.FindCollectionByNameOrId("Analysis")
	if err != nil {
		t.Fatal(err)
	}
	relation := analysis.Fields.GetByName("created_by").(*core.RelationField)
	if relation.CollectionId != users.Id || relation.Required || relation.MaxSelect != 1 || relation.CascadeDelete {
		t.Fatal("creator relation must target one user, allow legacy records, and preserve analyses on user deletion")
	}
	if !strings.Contains(strings.Join(analysis.Indexes, " "), "idx_analysis_creator_created") {
		t.Fatal("creator index is missing")
	}
	for index, owner := range []string{first.Id, second.Id, ""} {
		record := core.NewRecord(analysis)
		record.Set("analysis_id", []string{
			"01234567-89ab-4cde-8fab-0123456789ab", "11234567-89ab-4cde-8fab-0123456789ab", "21234567-89ab-4cde-8fab-0123456789ab",
		}[index])
		record.Set("original_text", "Event")
		record.Set("status", "Processing")
		record.Set("embedding_status", "Processing")
		record.Set("created_by", owner)
		if err := app.Save(record); err != nil {
			t.Fatal(err)
		}
		if index == 0 {
			record.Set("created_by", "missinguser0001")
			if err := app.Save(record); err == nil {
				t.Fatal("creator must reference an existing user")
			}
		}
	}
	if err := app.Delete(first); err != nil {
		t.Fatal(err)
	}
	records, err := app.FindAllRecords(analysis.Id)
	if err != nil || len(records) != 3 {
		t.Fatal("deleting a user must preserve its analyses", err)
	}
}
