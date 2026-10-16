package migrations

import (
	"github.com/pocketbase/pocketbase/core"
	m "github.com/pocketbase/pocketbase/migrations"
)

func init() {
	m.Register(func(app core.App) error {
		collection, err := app.FindCollectionByNameOrId("Analysis")
		if err != nil {
			return err
		}
		collection.Fields.Add(
			&core.JSONField{
				Name: "dates", MaxSize: 64 << 10,
				Help: "Original publication, primary event interval, rough duration estimate and exact source evidence. Null before extraction or on extraction failure.",
			},
			&core.JSONField{
				Name: "dates_error", MaxSize: 16 << 10,
				Help: "Nonfatal date extraction error: code and message. Null on success; independent of analysis status.",
			},
		)
		return app.Save(collection)
	}, func(app core.App) error {
		collection, err := app.FindCollectionByNameOrId("Analysis")
		if err != nil {
			return err
		}
		collection.Fields.RemoveByName("dates")
		collection.Fields.RemoveByName("dates_error")
		return app.Save(collection)
	})
}
