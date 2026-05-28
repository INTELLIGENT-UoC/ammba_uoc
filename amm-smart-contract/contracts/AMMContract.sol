// SPDX-License-Identifier: GPL-3.0-or-later
pragma solidity ^0.8.24;

/**
 * @title AMMContract
 * @notice On-chain audit anchor for the AMMBA clearing mechanism.
 *         The sigmoid price computation runs off-chain in the Clearing Node.
 *         This contract receives the result, validates it, stores it, and
 *         emits a MarketCleared event for transparency.
 *
 *         All uint256 energy/price values are scaled × 10000
 *         (NODE_FLOAT_SCALING_FACTOR matching GSY DEX convention).
 */
contract AMMContract {
    // ── Constants ──────────────────────────────────────────────────────
    uint256 public constant SCALING_FACTOR = 10000;

    // ── Roles ─────────────────────────────────────────────────────────
    address public owner;
    address public clearingNode;

    // ── Community parameters ──────────────────────────────────────────
    struct CommunityParams {
        uint256 kUpper;     // retail buy price  (ct/kWh × 10000)
        uint256 kLower;     // feed-in tariff    (ct/kWh × 10000)
        uint256 theta;      // sigmoid midpoint  (× 10000)
        uint256 steepness;  // sigmoid steepness (× 10000)
        bool    exists;
    }

    mapping(bytes32 => CommunityParams) public communityParams;

    // ── Clearing results ──────────────────────────────────────────────
    struct ClearingResult {
        bytes32 communityUuid;
        uint256 timeSlot;
        uint256 totalSupply;    // kWh × 10000
        uint256 totalDemand;    // kWh × 10000
        uint256 clearingPrice;  // ct/kWh × 10000
        address caller;
        uint256 blockTimestamp;
        bool    exists;
    }

    mapping(bytes32 => ClearingResult) public clearingResults;

    // ── Events ────────────────────────────────────────────────────────
    event MarketCleared(
        bytes32 indexed marketId,
        bytes32 indexed communityUuid,
        uint256 timeSlot,
        uint256 totalSupply,
        uint256 totalDemand,
        uint256 clearingPrice,
        uint256 blockTimestamp
    );

    event CommunityParamsUpdated(
        bytes32 indexed communityUuid,
        uint256 kUpper,
        uint256 kLower,
        uint256 theta,
        uint256 steepness
    );

    event ClearingNodeUpdated(address indexed newClearingNode);

    // ── Modifiers ─────────────────────────────────────────────────────
    modifier onlyOwner() {
        require(msg.sender == owner, "AMMContract: caller is not owner");
        _;
    }

    modifier onlyClearingNode() {
        require(
            msg.sender == clearingNode,
            "AMMContract: caller is not clearing node"
        );
        _;
    }

    // ── Constructor ───────────────────────────────────────────────────
    constructor(address _clearingNode) {
        owner = msg.sender;
        clearingNode = _clearingNode;
    }

    // ── Core functions ────────────────────────────────────────────────

    /**
     * @notice Record a market clearing result on-chain.
     * @dev    The sigmoid price is computed off-chain. This function validates
     *         that the price falls within [kLower, kUpper] for the community
     *         (if community params are set) and stores the result.
     */
    function clearMarket(
        bytes32 marketId,
        bytes32 communityUuid,
        uint256 timeSlot,
        uint256 totalSupply,
        uint256 totalDemand,
        uint256 clearingPrice
    ) external onlyClearingNode returns (bool) {
        require(
            !clearingResults[marketId].exists,
            "AMMContract: market already cleared"
        );

        // Validate price bounds if community params are configured
        if (communityParams[communityUuid].exists) {
            CommunityParams storage params = communityParams[communityUuid];
            require(
                clearingPrice >= params.kLower && clearingPrice <= params.kUpper,
                "AMMContract: price outside [kLower, kUpper]"
            );
        }

        clearingResults[marketId] = ClearingResult({
            communityUuid: communityUuid,
            timeSlot: timeSlot,
            totalSupply: totalSupply,
            totalDemand: totalDemand,
            clearingPrice: clearingPrice,
            caller: msg.sender,
            blockTimestamp: block.timestamp,
            exists: true
        });

        emit MarketCleared(
            marketId,
            communityUuid,
            timeSlot,
            totalSupply,
            totalDemand,
            clearingPrice,
            block.timestamp
        );

        return true;
    }

    // ── Admin functions ───────────────────────────────────────────────

    function setCommunityParams(
        bytes32 communityUuid,
        uint256 kUpper,
        uint256 kLower,
        uint256 theta,
        uint256 steepness
    ) external onlyOwner {
        require(kUpper >= kLower, "AMMContract: kUpper must be >= kLower");

        communityParams[communityUuid] = CommunityParams({
            kUpper: kUpper,
            kLower: kLower,
            theta: theta,
            steepness: steepness,
            exists: true
        });

        emit CommunityParamsUpdated(communityUuid, kUpper, kLower, theta, steepness);
    }

    function setClearingNode(address _clearingNode) external onlyOwner {
        clearingNode = _clearingNode;
        emit ClearingNodeUpdated(_clearingNode);
    }

    // ── View functions ────────────────────────────────────────────────

    function getClearingResult(bytes32 marketId)
        external
        view
        returns (
            uint256 timeSlot,
            uint256 supply,
            uint256 demand,
            uint256 price
        )
    {
        ClearingResult storage result = clearingResults[marketId];
        require(result.exists, "AMMContract: no result for market");
        return (
            result.timeSlot,
            result.totalSupply,
            result.totalDemand,
            result.clearingPrice
        );
    }

    function getCommunityParams(bytes32 communityUuid)
        external
        view
        returns (
            uint256 kUpper,
            uint256 kLower,
            uint256 theta,
            uint256 steepness
        )
    {
        CommunityParams storage params = communityParams[communityUuid];
        require(params.exists, "AMMContract: no params for community");
        return (params.kUpper, params.kLower, params.theta, params.steepness);
    }
}
