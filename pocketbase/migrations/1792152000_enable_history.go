package migrations

import (
	"github.com/pocketbase/pocketbase/core"
	m "github.com/pocketbase/pocketbase/migrations"
	"github.com/pocketbase/pocketbase/tools/types"
)

func init() {
	m.Register(func(app core.App) error {
		collection, err := app.FindCollectionByNameOrId("Analysis")
		if err != nil {
			return err
		}
		rule := `@request.auth.collectionName = "users" && @request.auth.id != "" && created_by = @request.auth.id && status = "Complete"`
		collection.ListRule = types.Pointer(rule)
		collection.ViewRule = types.Pointer(rule)
		collection.AddIndex("idx_analysis_owner_created", false, "created_by, status, created, id", "")
		return app.Save(collection)
	}, nil)
}
