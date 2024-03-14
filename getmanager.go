package main

import (
    "encoding/json"
    "fmt"
    "io/ioutil"
    "net/http"
)



func getManagerData(){
	baseURL := "https://fantasy.premierleague.com/api/entry/2412613/history/"
    baseURL2 := "https://fantasy.premierleague.com/api/entry/7391201/history/"
    baseURL3 := "https://fantasy.premierleague.com/api/entry/2206475/history/"
    baseURL4 := "https://fantasy.premierleague.com/api/entry/84836/history/"
    resp, err := http.Get(baseURL)
    resp2, err := http.Get(baseURL2)
    resp3, err := http.Get(baseURL3)    
    resp4, err := http.Get(baseURL4)
    if err != nil {
        panic(err)
    }
    defer resp.Body.Close()

    body, err := ioutil.ReadAll(resp.Body)
    if err != nil {
        panic(err)
    }

    body2, err := ioutil.ReadAll(resp2.Body)
    body3, err := ioutil.ReadAll(resp3.Body)
    body4, err := ioutil.ReadAll(resp4.Body)

    var result map[string]interface{}
    var result2 map[string]interface{}
    var result3 map[string]interface{}
    var result4 map[string]interface{}
    json.Unmarshal(body, &result)
    json.Unmarshal(body2, &result2)
    json.Unmarshal(body3, &result3)
    json.Unmarshal(body4, &result4)

    managerData := map[string]map[string]interface{}{
        "MvDeez nutmegs": result,
        "Borgies Fantasy hehe": result2,
        "Daddys dingleberries": result3,
        "Ange Management �": result4,
    }
    

    b, err := json.MarshalIndent(managerData, "", "  ")
    if err != nil {
        fmt.Println("error:", err)
    }

	err = ioutil.WriteFile("managerData.json", b, 0644)
	if err != nil {
    panic(err)
	}


    fmt.Print("Done loading manager data")
	
}