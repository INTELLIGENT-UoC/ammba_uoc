const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AMMContract", function () {
  let contract;
  let owner, clearingNode, other;

  const SCALING = 10000n;

  // Community params: kUpper=28.5, kLower=8.0, theta=1.0, steepness=2.5
  const communityUuid = ethers.encodeBytes32String("community_1");
  const kUpper = 285000n;   // 28.5 ct/kWh × 10000
  const kLower = 80000n;    // 8.0  ct/kWh × 10000
  const theta = 10000n;     // 1.0 × 10000
  const steepness = 25000n; // 2.5 × 10000

  beforeEach(async function () {
    [owner, clearingNode, other] = await ethers.getSigners();
    const AMMContract = await ethers.getContractFactory("AMMContract");
    contract = await AMMContract.deploy(clearingNode.address);
    await contract.waitForDeployment();
  });

  describe("Deployment", function () {
    it("sets the owner correctly", async function () {
      expect(await contract.owner()).to.equal(owner.address);
    });

    it("sets the clearing node correctly", async function () {
      expect(await contract.clearingNode()).to.equal(clearingNode.address);
    });

    it("exposes the scaling factor constant", async function () {
      expect(await contract.SCALING_FACTOR()).to.equal(SCALING);
    });
  });

  describe("setCommunityParams", function () {
    it("allows owner to set community parameters", async function () {
      await expect(
        contract.setCommunityParams(communityUuid, kUpper, kLower, theta, steepness)
      )
        .to.emit(contract, "CommunityParamsUpdated")
        .withArgs(communityUuid, kUpper, kLower, theta, steepness);

      const params = await contract.getCommunityParams(communityUuid);
      expect(params[0]).to.equal(kUpper);
      expect(params[1]).to.equal(kLower);
      expect(params[2]).to.equal(theta);
      expect(params[3]).to.equal(steepness);
    });

    it("rejects non-owner", async function () {
      await expect(
        contract
          .connect(other)
          .setCommunityParams(communityUuid, kUpper, kLower, theta, steepness)
      ).to.be.revertedWith("AMMContract: caller is not owner");
    });

    it("rejects kUpper < kLower", async function () {
      await expect(
        contract.setCommunityParams(communityUuid, kLower, kUpper, theta, steepness)
      ).to.be.revertedWith("AMMContract: kUpper must be >= kLower");
    });
  });

  describe("clearMarket", function () {
    const marketId = ethers.encodeBytes32String("market_slot_1");
    const timeSlot = 1700000000n;
    const totalSupply = 125000n; // 12.5 kWh × 10000
    const totalDemand = 100000n; // 10.0 kWh × 10000
    const clearingPrice = 150000n; // 15.0 ct/kWh × 10000

    beforeEach(async function () {
      await contract.setCommunityParams(
        communityUuid,
        kUpper,
        kLower,
        theta,
        steepness
      );
    });

    it("records clearing and emits MarketCleared event", async function () {
      const tx = await contract
        .connect(clearingNode)
        .clearMarket(
          marketId,
          communityUuid,
          timeSlot,
          totalSupply,
          totalDemand,
          clearingPrice
        );

      const block = await ethers.provider.getBlock(tx.blockNumber);
      await expect(tx)
        .to.emit(contract, "MarketCleared")
        .withArgs(
          marketId,
          communityUuid,
          timeSlot,
          totalSupply,
          totalDemand,
          clearingPrice,
          block.timestamp
        );
    });

    it("stores the clearing result retrievable via getClearingResult", async function () {
      await contract
        .connect(clearingNode)
        .clearMarket(
          marketId,
          communityUuid,
          timeSlot,
          totalSupply,
          totalDemand,
          clearingPrice
        );

      const result = await contract.getClearingResult(marketId);
      expect(result[0]).to.equal(timeSlot);
      expect(result[1]).to.equal(totalSupply);
      expect(result[2]).to.equal(totalDemand);
      expect(result[3]).to.equal(clearingPrice);
    });

    it("rejects duplicate clearing for same market_id", async function () {
      await contract
        .connect(clearingNode)
        .clearMarket(
          marketId,
          communityUuid,
          timeSlot,
          totalSupply,
          totalDemand,
          clearingPrice
        );

      await expect(
        contract
          .connect(clearingNode)
          .clearMarket(
            marketId,
            communityUuid,
            timeSlot,
            totalSupply,
            totalDemand,
            clearingPrice
          )
      ).to.be.revertedWith("AMMContract: market already cleared");
    });

    it("rejects non-clearing-node caller", async function () {
      await expect(
        contract
          .connect(other)
          .clearMarket(
            marketId,
            communityUuid,
            timeSlot,
            totalSupply,
            totalDemand,
            clearingPrice
          )
      ).to.be.revertedWith("AMMContract: caller is not clearing node");
    });

    it("rejects price outside [kLower, kUpper] bounds", async function () {
      const tooHigh = kUpper + 1n;
      await expect(
        contract
          .connect(clearingNode)
          .clearMarket(
            marketId,
            communityUuid,
            timeSlot,
            totalSupply,
            totalDemand,
            tooHigh
          )
      ).to.be.revertedWith("AMMContract: price outside [kLower, kUpper]");

      const tooLow = kLower - 1n;
      await expect(
        contract
          .connect(clearingNode)
          .clearMarket(
            marketId,
            communityUuid,
            timeSlot,
            totalSupply,
            totalDemand,
            tooLow
          )
      ).to.be.revertedWith("AMMContract: price outside [kLower, kUpper]");
    });

    it("allows clearing without community params set (no bounds check)", async function () {
      const unknownCommunity = ethers.encodeBytes32String("unknown");
      await expect(
        contract
          .connect(clearingNode)
          .clearMarket(
            marketId,
            unknownCommunity,
            timeSlot,
            totalSupply,
            totalDemand,
            clearingPrice
          )
      ).not.to.be.reverted;
    });

    it("allows price at exact bounds (kLower and kUpper)", async function () {
      const marketLow = ethers.encodeBytes32String("market_low");
      await expect(
        contract
          .connect(clearingNode)
          .clearMarket(
            marketLow,
            communityUuid,
            timeSlot,
            totalSupply,
            totalDemand,
            kLower
          )
      ).not.to.be.reverted;

      const marketHigh = ethers.encodeBytes32String("market_high");
      await expect(
        contract
          .connect(clearingNode)
          .clearMarket(
            marketHigh,
            communityUuid,
            timeSlot,
            totalSupply,
            totalDemand,
            kUpper
          )
      ).not.to.be.reverted;
    });
  });

  describe("setClearingNode", function () {
    it("allows owner to update the clearing node", async function () {
      await expect(contract.setClearingNode(other.address))
        .to.emit(contract, "ClearingNodeUpdated")
        .withArgs(other.address);
      expect(await contract.clearingNode()).to.equal(other.address);
    });

    it("rejects non-owner", async function () {
      await expect(
        contract.connect(other).setClearingNode(other.address)
      ).to.be.revertedWith("AMMContract: caller is not owner");
    });
  });

  describe("View functions edge cases", function () {
    it("reverts getClearingResult for unknown market", async function () {
      const unknown = ethers.encodeBytes32String("nonexistent");
      await expect(contract.getClearingResult(unknown)).to.be.revertedWith(
        "AMMContract: no result for market"
      );
    });

    it("reverts getCommunityParams for unknown community", async function () {
      const unknown = ethers.encodeBytes32String("nonexistent");
      await expect(contract.getCommunityParams(unknown)).to.be.revertedWith(
        "AMMContract: no params for community"
      );
    });
  });
});
