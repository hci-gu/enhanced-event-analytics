package migrations

import (
	"github.com/pocketbase/pocketbase/core"
	m "github.com/pocketbase/pocketbase/migrations"
)

func init() {
	m.Register(addLocationFields, removeLocationFields)
}

func addLocationFields(app core.App) error {
	collection, err := app.FindCollectionByNameOrId("Analysis")
	if err != nil {
		return err
	}
	collection.Fields.Add(
		&core.JSONField{Name: "location", MaxSize: 256 << 10,
			Help: "Event locations with roles, exact evidence, Geoapify coordinates, precision and attribution. Null before extraction or when disabled/failed."},
		&core.JSONField{Name: "location_error", MaxSize: 16 << 10,
			Help: "Nonfatal location error or limit warning. Available locations and category results are preserved."},
	)
	return app.Save(collection)
}

func removeLocationFields(app core.App) error {
	collection, err := app.FindCollectionByNameOrId("Analysis")
	if err != nil {
		return err
	}
	collection.Fields.RemoveByName("location")
	collection.Fields.RemoveByName("location_error")
	return app.Save(collection)
}
