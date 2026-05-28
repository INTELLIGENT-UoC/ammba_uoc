const { ethers } = require("hardhat");

async function main() {
  const clearingNodeAddress = process.env.CLEARING_NODE_ADDRESS;
  if (!clearingNodeAddress) {
    throw new Error("CLEARING_NODE_ADDRESS environment variable is required");
  }

  console.log("Deploying AMMContract...");
  console.log("Clearing node address:", clearingNodeAddress);

  const AMMContract = await ethers.getContractFactory("AMMContract");
  const contract = await AMMContract.deploy(clearingNodeAddress);
  await contract.waitForDeployment();

  const address = await contract.getAddress();
  console.log("AMMContract deployed to:", address);

  // Optionally set community params
  if (process.env.COMMUNITY_UUID) {
    const communityUuid = ethers.encodeBytes32String(process.env.COMMUNITY_UUID);
    const kUpper = BigInt(process.env.K_UPPER || "285000");
    const kLower = BigInt(process.env.K_LOWER || "80000");
    const theta = BigInt(process.env.THETA || "10000");
    const steepness = BigInt(process.env.STEEPNESS || "25000");

    console.log("Setting community params for:", process.env.COMMUNITY_UUID);
    const tx = await contract.setCommunityParams(
      communityUuid,
      kUpper,
      kLower,
      theta,
      steepness
    );
    await tx.wait();
    console.log("Community params set.");
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
