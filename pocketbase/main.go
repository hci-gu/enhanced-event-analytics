package main

import (
	"log"
	"os"

	_ "pocketbase/migrations"

	"github.com/pocketbase/pocketbase"
	"github.com/pocketbase/pocketbase/apis"
	"github.com/pocketbase/pocketbase/core"
	"github.com/pocketbase/pocketbase/plugins/migratecmd"
)

func main() {
	app := pocketbase.New()
	migratecmd.MustRegister(app, app.RootCmd, migratecmd.Config{Automigrate: false})
	app.OnRecordAfterCreateSuccess("Analysis").BindFunc(logAnalysisSave("create"))
	app.OnRecordAfterUpdateSuccess("Analysis").BindFunc(logAnalysisSave("update"))

	app.OnServe().BindFunc(func(se *core.ServeEvent) error {
		// serves static files from the provided public dir (if exists)
		se.Router.GET("/{path...}", apis.Static(os.DirFS("./pb_public"), false))

		return se.Next()
	})

	if err := app.Start(); err != nil {
		log.Fatal(err)
	}
}

func logAnalysisSave(operation string) func(*core.RecordEvent) error {
	return func(e *core.RecordEvent) error {
		e.App.Logger().Info("Analysis record saved",
			"operation", operation,
			"record_id", e.Record.Id,
			"analysis_id", e.Record.GetString("analysis_id"),
			"created_by", e.Record.GetString("created_by"),
			"status", e.Record.GetString("status"),
			"embedding_status", e.Record.GetString("embedding_status"),
		)
		return e.Next()
	}
}
