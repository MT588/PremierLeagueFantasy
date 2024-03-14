package main 
import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
)

func LoadData() {
    baseURL := "https://fantasy.premierleague.com/api/"
    resp, err := http.Get(baseURL + "bootstrap-static/")
    if err != nil {
        panic(err)
    }
    defer resp.Body.Close()

    body, err := ioutil.ReadAll(resp.Body)
    if err != nil {
        panic(err)
    }

    var result map[string]interface{}
    json.Unmarshal(body, &result)

    b, err := json.MarshalIndent(result, "", "  ")
    if err != nil {
        fmt.Println("error:", err)
    }

	err = ioutil.WriteFile("AllData.json", b, 0644)
	if err != nil {
    panic(err)
	}

    fmt.Print("Done loading data")

	
}