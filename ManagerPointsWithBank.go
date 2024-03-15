package main 

import (
	"fmt"
	"encoding/json"
	"io/ioutil"
)

type Manager struct {
	Current	[]Current 	`json:"current"`
}


func PointsWithBank(){
	data, err := ioutil.ReadFile("managerData.json")
	if err != nil {
		panic(err)
	}
	var managerData map[string]Manager
	err = json.Unmarshal(data, &managerData)
	if err != nil {
		panic(err)
	}

	var managerNames []string
    for name := range managerData {
        managerNames = append(managerNames, name)
    }

	for name, manager := range managerData {
		pointsOnBench := 0
		for _, j := range manager.Current{
			pointsOnBench += j.PointsOnBench
		}
		allPoints := manager.Current[len(manager.Current)-1].TotalPoints + pointsOnBench
		fmt.Printf("%-25s \n\tTotal points:%d \n\tTotal points on bench:%d \n\tTotal points with bench:%d\n", name +":",manager.Current[len(manager.Current)-1].TotalPoints,pointsOnBench, allPoints)
	}
	
	// fmt.Printf("%-25s %8d\n", managerNames[0]+":", managerData[managerNames[0]].Current[len(managerData[managerNames[0]].Current)-1].TotalPoints,)
	// fmt.Printf("%-25s %8d\n", managerNames[1]+":", managerData[managerNames[1]].Current[len(managerData[managerNames[1]].Current)-1].TotalPoints,)
	// fmt.Printf("%-25s %8d\n", managerNames[2]+":", managerData[managerNames[2]].Current[len(managerData[managerNames[2]].Current)-1].TotalPoints,)
	// fmt.Printf("%-25s %8d\n", managerNames[3]+":", managerData[managerNames[3]].Current[len(managerData[managerNames[3]].Current)-1].TotalPoints,)
	
}