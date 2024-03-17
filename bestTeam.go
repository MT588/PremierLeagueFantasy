package main

import (
	"encoding/json"
	"fmt"
	"os"
    "github.com/ernestosuarez/itertools"
)

type PlayerData struct {
    Name    	string    `json:"name"`
    History 	[]History `json:"history"`
    ID          int       `json:"id"`
    Team        int       `json:"team"`
    Position    int       `json:"position"`
    Cost        float64   `json:"cost"`
}


type History struct {
    Assists                    int     `json:"assists"`
    Bonus                      int     `json:"bonus"`
    Bps                        int     `json:"bps"`
    Clean_sheets               int     `json:"clean_sheets"`
    Creativity                 float64 `json:"creativity"`
    Element                    int     `json:"element"`
    Expected_assists           float64 `json:"expected_assists"`
    Expected_goal_involvements float64 `json:"expected_goal_involvements"`
    Expected_goals             float64 `json:"expected_goals"`
    Expected_goals_conceded    float64 `json:"expected_goals_conceded"`
    Fixtures                   int     `json:"fixtures"`
    Goals_conceded             int     `json:"goals_conceded"`
    Goals_scored               int     `json:"goals_scored"`
    Ict_index                  float64 `json:"ict_index"`
    Influence                  float64 `json:"influence"`
    Kickoff_time               string  `json:"kickoff_time"`
    Minutes                    int     `json:"minutes"`
    Opponent_team              int     `json:"opponent_team"`
    Own_goals                  int     `json:"own_goals"`
    Penalties_missed           int     `json:"penalties_missed"`
    Penalties_saved            int     `json:"penalties_saved"`
    Red_cards                  int     `json:"red_cards"`
    Round                      int     `json:"round"`
    Saves                      int     `json:"saves"`
    Selected                   int     `json:"selected"`
    Team_a_score               int     `json:"team_a_score"`
    Team_h_score               int     `json:"team_h_score"`
    Threat                     float64 `json:"threat"`
    Total_points               int     `json:"total_points"`
    Transfers_balance          int     `json:"transfers_balance"`
    Transfers_in               int     `json:"transfers_in"`
    Transfers_out              int     `json:"transfers_out"`
    Value                      float64 `json:"value"`
    Was_home                   bool    `json:"was_home"`
    Yellow_cards               int     `json:"yellow_cards"`
}


type Team struct{
    Players         []PlayerData
    TotalPoints     int
    TotalCost       float64
}

func (team Team) String() (res string) {
    res += fmt.Sprintf("Total Points: %v\nTotal Cost: %v\n", team.TotalPoints, team.TotalCost)
    res += "Players:\n"
    for _, player := range team.Players {
        res += fmt.Sprintf("%v,", player.Name)
    }
    return 
    
}
func bestTeamCalculation() {
	byteValue, _ := os.ReadFile("player.json")

	var result map[string][]PlayerData
	json.Unmarshal(byteValue, &result)

    var bestTeam Team
    bestTeam.TotalPoints = 0
    bestTeam.TotalCost = 0.0  

    totalAmountOfGoalKeepers := 0
    totalAmountOfDefenders := 0
    totalAmountOfMidfielders := 0
    totalAmountOfForwards := 0
    for _, player := range result["player"] {
        if player.Position == 1 {
            totalAmountOfGoalKeepers++
        } else if player.Position == 2 {
            totalAmountOfDefenders++
        } else if player.Position == 3 {
            totalAmountOfMidfielders++
        } else if player.Position == 4 {
            totalAmountOfForwards++
        }
    }

    GoalKeepers := make(itertools.List, 0, totalAmountOfGoalKeepers)
    for i := range result["player"] {
        if result["player"][i].Position == 1 {
            GoalKeepers = append(GoalKeepers, i)
        }
    }

    Defenders := make(itertools.List, 0, totalAmountOfDefenders)
    for i := range result["player"] {
        if result["player"][i].Position == 2 {
            Defenders = append(Defenders, i)
        }
    }

    Midfielders := make(itertools.List, 0, totalAmountOfMidfielders)
    for i := range result["player"] {
        if result["player"][i].Position == 3 {
            Midfielders = append(Midfielders, i)
        }
    }

    Forwards := make(itertools.List, 0, totalAmountOfForwards)
    for i := range result["player"] {
        if result["player"][i].Position == 4 {
            Forwards = append(Forwards, i)
        }
    }

    for comboGK := range itertools.CombinationsList(GoalKeepers, 2) {
        for comboDEF := range itertools.CombinationsList(Defenders, 5) {
            for comboMID := range itertools.CombinationsList(Midfielders, 5) {
                for comboFWD := range itertools.CombinationsList(Forwards, 3) {
                    currentTeamCost := 0.0
                    currentTeamPoints := 0
                    for _, p := range comboGK {
                        player := result["player"][p.(int)]
                        currentTeamCost += player.Cost
                        for _, history := range player.History {
                            currentTeamPoints += history.Total_points
                        }
                    }
                    for _, p := range comboDEF {
                        player := result["player"][p.(int)]
                        currentTeamCost += player.Cost
                        for _, history := range player.History {
                            currentTeamPoints += history.Total_points
                        }
                    }
                    for _, p := range comboMID {
                        player := result["player"][p.(int)]
                        currentTeamCost += player.Cost
                        for _, history := range player.History {
                            currentTeamPoints += history.Total_points
                        }
                    }
                    for _, p := range comboFWD {
                        player := result["player"][p.(int)]
                        currentTeamCost += player.Cost
                        for _, history := range player.History {
                            currentTeamPoints += history.Total_points
                        }
                    }
                    if currentTeamCost > 1000.0 {
                        break
                    }
                    
                    if currentTeamPoints > bestTeam.TotalPoints {
                        bestTeam.TotalPoints = currentTeamPoints
                        bestTeam.TotalCost = currentTeamCost
                        bestTeam.Players = make([]PlayerData, 0, 11)
                        for _, p := range comboGK {
                            bestTeam.Players = append(bestTeam.Players, result["player"][p.(int)])
                        }
                        for _, p := range comboDEF {
                            bestTeam.Players = append(bestTeam.Players, result["player"][p.(int)])
                        }
                        for _, p := range comboMID {
                            bestTeam.Players = append(bestTeam.Players, result["player"][p.(int)])
                        }
                        for _, p := range comboFWD {
                            bestTeam.Players = append(bestTeam.Players, result["player"][p.(int)])
                        }
                        fmt.Println(bestTeam)
                    }
                }
                
            }                
        }
    }

    // for _, player := range result["player"]{
    //     if len(team.Players) == 11{
    //         break
    //     }
    //     total_points := 0
    //     team.Players = append(team.Players, player)
    //     for _, history := range player.History{
    //         total_points += history.Total_points
    //     }
    //     team.TotalPoints += total_points
    //     team.TotalCost += player.Cost
    // }

    fmt.Println(bestTeam)
	

}