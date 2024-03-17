package main

import (
	"encoding/json"
	"fmt"
	"os"
)

type PlayerData struct {
    Name    	string    `json:"name"`
    History 	[]History `json:"history"`
    ID          int       `json:"id"`
    Team        string    `json:"team"`
    ElementType string    `json:"position"`
    NowCost     float64   `json:"cost"`
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

func bestTeamCalculation() {
	byteValue, _ := os.ReadFile("player.json")

	var result map[string][]PlayerData
	json.Unmarshal(byteValue, &result)

	fmt.Println(result["player"][0])

}