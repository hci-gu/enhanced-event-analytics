package migrations

import (
	"database/sql"
	"errors"
	"fmt"
	"github.com/pocketbase/pocketbase/core"
	m "github.com/pocketbase/pocketbase/migrations"
	"github.com/pocketbase/pocketbase/tools/types"
)

func init() {
	m.Register(func(app core.App) error {
		// PocketBase's system migrations already create a default users collection.
		// Reuse it so existing accounts and token secrets are preserved.
		users, err := app.FindCollectionByNameOrId("users")
		if errors.Is(err, sql.ErrNoRows) {
			users = core.NewAuthCollection("users")
		} else if err != nil {
			return err
		}
		if !users.IsAuth() {
			return fmt.Errorf("users must be an auth collection")
		}
		users.Fields.GetByName("email").(*core.EmailField).Required = true
		users.Fields.GetByName("password").(*core.PasswordField).Min = 8
		users.AuthToken.Duration = 7 * 24 * 60 * 60
		users.PasswordAuth.Enabled = true
		users.PasswordAuth.IdentityFields = []string{"email"}
		users.AuthRule = types.Pointer("")
		users.CreateRule = nil
		users.ListRule = nil
		users.ViewRule = nil
		users.UpdateRule = nil
		users.DeleteRule = nil
		// Public registration is mediated by FastAPI; record rules stay locked.
		// No mail provider is needed for this initial password-only flow.
		users.AuthAlert.Enabled = false
		if err := app.Save(users); err != nil {
			return err
		}
		analysis, err := app.FindCollectionByNameOrId("Analysis")
		if err != nil {
			return err
		}
		analysis.Fields.Add(&core.RelationField{
			Name: "created_by", CollectionId: users.Id, MaxSelect: 1,
			CascadeDelete: false,
			Help:          "Verified users identity assigned by the backend; empty for legacy analyses.",
		})
		analysis.AddIndex("idx_analysis_creator_created", false, "created_by, created", "")
		return app.Save(analysis)
	}, nil)
}
