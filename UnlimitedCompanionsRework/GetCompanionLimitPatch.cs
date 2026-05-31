using HarmonyLib;
using TaleWorlds.CampaignSystem;
using TaleWorlds.CampaignSystem.GameComponents;

namespace UnlimitedCompanionsRework
{
    [HarmonyPatch(typeof(DefaultClanTierModel), "GetCompanionLimit")]
    public class GetCompanionLimitPatch
    {
        public static bool Prefix(Clan clan, ref int __result)
        {
            if (clan == Clan.PlayerClan)
            {
                __result = 1000;
                return false; // Skip the original method
            }
            return true; // Run original method for NPC clans
        }
    }
}
