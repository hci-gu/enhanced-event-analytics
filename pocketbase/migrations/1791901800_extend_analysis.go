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
			&core.TextField{
				Name: "original_text", Required: true, Max: 2 << 20,
				Help: "Immutable snapshot of the trimmed input analyzed by the backend; evidence quotes refer to this text.",
			},
			&core.DateField{
				Name: "finished_at",
				Help: "UTC time when category analysis becomes Complete or Failed; empty while Processing. Independent of embedding completion.",
			},
			&core.SelectField{
				Name: "embedding_status", Required: true, MaxSelect: 1,
				Values: []string{"Processing", "Failed", "Complete"},
				Help:   "Embedding generation status, independent of category analysis status. Complete means the vector was generated, not indexed.",
			},
		)
		return app.Save(collection)
	}, nil)
}
