package main

import (
    "encoding/json"
    "fmt"
    "io/ioutil"
    "net/http"
)



type Data struct {
    Elements []Player `json:"elements"`
}



func getAllPlayerData() {
	data, err := ioutil.ReadFile("AllData.json")
	if err != nil {
		panic(err)
	}

	var result2 Data
    err = json.Unmarshal(data, &result2)
    if err != nil {
        panic(err)
    }

	playerData := make(map[string][]map[string]interface{})
	playerData["player"] = []map[string]interface{}{}

	for _, player := range result2.Elements {
		baseURL := "https://fantasy.premierleague.com/api/"
		extraURL := "element-summary/" + fmt.Sprint(player.ID) + "/"
		resp, err := http.Get(baseURL + extraURL)
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
		result["name"] = player.FirstName + " " + player.SecondName
		result["id"] = player.ID
		result["team"] = player.Team
		result["position"] = player.ElementType
		result["cost"] = player.NowCost
		playerData["player"] = append(playerData["player"], result) 
	}

	b, err := json.MarshalIndent(playerData, "", "  ")
	if err != nil {
		fmt.Println("error:", err)
	}

	err = ioutil.WriteFile("player.json", b, 0644)
	if err != nil {
		panic(err)
	}

	fmt.Println("Done loading playerdata")
}

