package main

import (
    "encoding/json"
    "fmt"
    "io/ioutil"
    "net/http"
)

var mapData map[string]int

func init() {
    mapData = map[string]int{
        "MvDeez nutmegs": 2412613,
        "Borgies Fantasy hehe": 7391201,
        "Daddys dingleberries": 2206475,
        "Ange Management �": 84836,
        "Shaw me dias": 3669510,
    }
}



func getManagerData(){
	baseURL := "https://fantasy.premierleague.com/api/entry/"
    managerData := make(map[string]map[string]interface{})

    for name, id := range mapData {
        resp, err := http.Get(baseURL + fmt.Sprint(id) + "/history/")
        if err != nil {
            panic(err)
        }
        defer resp.Body.Close()
        body, err := ioutil.ReadAll(resp.Body)
        var result map[string]interface{}
        json.Unmarshal(body, &result)
        managerData[name] = result
    }

    b, err := json.MarshalIndent(managerData, "", "  ")
    if err != nil {
        fmt.Println("error:", err)
    }

	err = ioutil.WriteFile("managerData.json", b, 0644)
	if err != nil {
    panic(err)
	}

    fmt.Print("Done loading manager data \n")
	
}