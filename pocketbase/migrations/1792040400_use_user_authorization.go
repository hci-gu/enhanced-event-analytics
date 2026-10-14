package migrations

import (
	"github.com/pocketbase/pocketbase/core"
	m "github.com/pocketbase/pocketbase/migrations"
	"github.com/pocketbase/pocketbase/tools/types"
)

func init() {
	m.Register(func(app core.App) error {
		users, err := app.FindCollectionByNameOrId("users")
		if err != nil {
			return err
		}
		// Python forwards only email/password/passwordConfirm. Keep privileged
		// fields out of anonymous registration at the database boundary too.
		users.CreateRule = types.Pointer(`@request.body.verified:isset = false && @request.body.tokenKey:isset = false && @request.body.emailVisibility:isset = false && @request.body.id:isset = false`)
		if err := app.Save(users); err != nil {
			return err
		}
		analysis, err := app.FindCollectionByNameOrId("Analysis")
		if err != nil {
			return err
		}
		analysis.CreateRule = types.Pointer(`@request.auth.collectionName = "users" && @request.auth.id != "" && @request.body.created_by = @request.auth.id`)
		analysis.UpdateRule = types.Pointer(`@request.auth.collectionName = "users" && @request.auth.id != "" && created_by = @request.auth.id && @request.body.created_by:changed = false && @request.body.analysis_id:changed = false && @request.body.original_text:changed = false`)
		// Listing, viewing, and deletion stay locked until Python exposes them.
		return app.Save(analysis)
	}, nil)
}
