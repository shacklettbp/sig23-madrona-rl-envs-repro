#pragma once

#include <madrona/taskgraph.hpp>
#include <madrona/math.hpp>
#include <madrona/custom_context.hpp>
#include <madrona/components.hpp>

#include <vector>

#include "init.hpp"

#define NUM_MOVES 6
#define MAX_SIZE 256
#define MAX_NUM_PLAYERS 2
#define MAX_NUM_INGREDIENTS 3

#define NUM_RECIPES ((MAX_NUM_INGREDIENTS + 1) * (MAX_NUM_INGREDIENTS + 1))

using IntVector = std::vector<int64_t>;

namespace Overcooked {

    enum ActionT: int32_t { NORTH=0, SOUTH=1, EAST=2, WEST=3, STAY=4, INTERACT=5 };
    enum TerrainT: uint8_t { AIR, POT, COUNTER, ONION_SOURCE, TOMATO_SOURCE, DISH_SOURCE, SERVING};
    enum ObjectT: uint8_t { NONE, TOMATO, ONION, DISH, SOUP};

    struct RendererInitStub {};
    struct Config {
        IntVector terrain;
        int64_t height;
        int64_t width;
        int64_t num_players;
        IntVector start_player_x;
        IntVector start_player_y;
        int64_t placement_in_pot_rew;
        int64_t dish_pickup_rew;
        int64_t soup_pickup_rew;
        IntVector recipe_values;
        IntVector recipe_times;
        int64_t horizon;        
    };

    struct Object {
        ObjectT name = ObjectT::NONE;
        uint8_t num_onions = 0;
        uint8_t num_tomatoes = 0;
        int8_t cooking_tick = -1;

        uint8_t num_ingredients()
        {
            return num_onions + num_tomatoes;
        }

        uint8_t get_recipe()
        {
            return (MAX_NUM_INGREDIENTS + 1) * num_onions + num_tomatoes;
        }
    };
    

    class Engine;

    struct WorldReset {
        int32_t resetNow;
    };

    struct WorldState {
        Object objects[MAX_SIZE];
        int32_t timestep;
        uint8_t size;

        uint8_t num_players;
        
        TerrainT terrain[MAX_SIZE];
        uint8_t height;
        uint8_t width;
        uint8_t start_player_x[MAX_NUM_PLAYERS];
        uint8_t start_player_y[MAX_NUM_PLAYERS];
        uint8_t placement_in_pot_rew;
        uint8_t dish_pickup_rew;
        uint8_t soup_pickup_rew;
        uint8_t recipe_values[NUM_RECIPES];
        uint8_t recipe_times[NUM_RECIPES];
        int64_t horizon;

        uint8_t num_pots;
        uint8_t pot_locs[MAX_SIZE];
        
        uint8_t num_counters;
        uint8_t counter_locs[MAX_SIZE];

        int64_t calculated_reward;
    };

    struct ActiveAgent {
        int32_t isActive;
    };

    struct Action {
        ActionT choice; // 6 discrete choices
    };

    struct Observation {
        int32_t x[MAX_SIZE * (5 * MAX_NUM_PLAYERS + 16)];
    };

    struct PlayerState {
        uint8_t position, orientation;
        uint8_t proposed_position, proposed_orientation;
        Object held_object;

        bool has_object() { return held_object.name != ObjectT::NONE; }
        Object& get_object() { return held_object; }
        void set_object(Object obj) { held_object = obj; }
        Object remove_object()
        {
            Object obj = held_object;
            held_object = {
                .name = ObjectT::NONE,
                .num_onions = 0,
                .num_tomatoes = 0,
                .cooking_tick = -1
            };
            return obj;
        }
        void update_pos_and_or()
        {
            position = proposed_position;
            orientation = proposed_orientation;
        }
        void update_or()
        {
            orientation = proposed_orientation;
        }
        void propose_pos_and_or(int32_t p, int32_t o)
        {
            proposed_position = p;
            proposed_orientation = o;
        }
    };

    struct AgentID {
        int32_t id;
    };
    
    struct ActionMask {
        int32_t isValid[NUM_MOVES];
    };

    struct Reward {
        float rew;
    };

    struct Agent : public madrona::Archetype<Action, Observation, PlayerState, AgentID, ActionMask, ActiveAgent, Reward> {};

    struct Sim : public madrona::WorldBase {
        static void registerTypes(madrona::ECSRegistry &registry, const Config &cfg);

        static void setupTasks(madrona::TaskGraph::Builder &builder, const Config &cfg);

        Sim(Engine &ctx, const Config& cfg, const WorldInit &init);

        EpisodeManager *episodeMgr;
        
        madrona::Entity *agents;
    };

    class Engine : public ::madrona::CustomContext<Engine, Sim> {
        using CustomContext::CustomContext;
    };

}
