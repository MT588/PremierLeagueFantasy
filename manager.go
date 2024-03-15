package main

type Current struct {
	Bank               int     `json:"bank"`
    Event              int     `json:"event"`
    EventTransfers     int     `json:"event_transfers"`
    EventTransfersCost int     `json:"event_transfers_cost"`
    OverallRank        int     `json:"overall_rank"`
    Points             int     `json:"points"`
    PointsOnBench      int     `json:"points_on_bench"`
    Rank               int     `json:"rank"`
    RankSort           int     `json:"rank_sort"`
    TotalPoints        int     `json:"total_points"`
    Value              int     `json:"value"`
}