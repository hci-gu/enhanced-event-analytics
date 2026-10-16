package main

import (
	"fmt"
	"log"
	"net"
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
		serveCommand, _, err := app.RootCmd.Find([]string{"serve"})
		if err != nil {
			return err
		}
		httpsAddress, err := serveCommand.PersistentFlags().GetString("https")
		if err != nil {
			return err
		}
		if err := validatePrivateListener(se.Server.Addr, httpsAddress); err != nil {
			return err
		}
		// serves static files from the provided public dir (if exists)
		se.Router.GET("/{path...}", apis.Static(os.DirFS("./pb_public"), false))

		return se.Next()
	})

	if err := app.Start(); err != nil {
		log.Fatal(err)
	}
}

func validatePrivateListener(address, httpsAddress string) error {
	// HTTPS and domain serving belong to the Python-facing reverse proxy.
	// PocketBase's HTTPS mode can also start a secondary HTTP listener.
	if httpsAddress != "" {
		return fmt.Errorf("PocketBase must use private loopback HTTP; terminate HTTPS at the Python reverse proxy")
	}
	host, _, err := net.SplitHostPort(address)
	if err != nil || net.ParseIP(host) == nil || !net.ParseIP(host).IsLoopback() {
		return fmt.Errorf("PocketBase must bind a loopback IP (for example 127.0.0.1:8090)")
	}
	return nil
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
