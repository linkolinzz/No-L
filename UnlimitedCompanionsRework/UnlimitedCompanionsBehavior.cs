using System;
using System.Collections.Generic;
using TaleWorlds.CampaignSystem;
using TaleWorlds.Core;

namespace UnlimitedCompanionsRework
{
    public class UnlimitedCompanionsBehavior : CampaignBehaviorBase
    {
        private List<string> _resetHeroes = new List<string>();

        public override void RegisterEvents()
        {
            CampaignEvents.OnSessionLaunchedEvent.AddNonSerializedListener(this, new Action<CampaignGameStarter>(OnSessionLaunched));
            CampaignEvents.NewCompanionAdded.AddNonSerializedListener(this, new Action<Hero>(OnNewCompanionAdded));
        }

        public override void SyncData(IDataStore dataStore)
        {
            dataStore.SyncData("UnlimitedCompanionsRework_ResetHeroes", ref _resetHeroes);
            if (_resetHeroes == null)
            {
                _resetHeroes = new List<string>();
            }
        }

        private void OnSessionLaunched(CampaignGameStarter starter)
        {
            ResetWanderersAndCompanions();
        }

        private void OnNewCompanionAdded(Hero companion)
        {
            if (companion != null)
            {
                ResetHero(companion);
            }
        }

        private void ResetWanderersAndCompanions()
        {
            foreach (Hero hero in Hero.AllAliveHeroes)
            {
                if (hero.IsWanderer || (hero.CompanionOf != null && hero.CompanionOf == Clan.PlayerClan))
                {
                    ResetHero(hero);
                }
            }
        }

        private void ResetHero(Hero hero)
        {
            if (hero == null || _resetHeroes.Contains(hero.StringId))
            {
                return;
            }

            try
            {
                // Reset level to 0
                hero.HeroDeveloper.SetInitialLevel(0);

                // Clear all skills
                foreach (SkillObject skill in TaleWorlds.Core.Game.Current.ObjectManager.GetObjectTypeList<SkillObject>())
                {
                    hero.HeroDeveloper.SetInitialSkillLevel(skill, 0);
                }

                // Give base attributes and remove focus manually by reflection or clearing traits since clear focuses API varies.
                hero.HeroDeveloper.ClearDeveloper();

                // Add the reset hero to the list
                _resetHeroes.Add(hero.StringId);
            }
            catch (Exception)
            {
                // Log exception silently or handle it
            }
        }
    }
}
