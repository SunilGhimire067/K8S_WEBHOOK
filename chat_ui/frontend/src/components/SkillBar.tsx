import { useEffect, useState } from "react";
import type { Skill } from "../types/chat";
import { fetchSkills } from "../api/chatApi";

interface Props {
  onSkillClick: (skill: Skill) => void;
  disabled: boolean;
}

export function SkillBar({ onSkillClick, disabled }: Props) {
  const [skills, setSkills] = useState<Skill[]>([]);

  useEffect(() => {
    fetchSkills()
      .then(setSkills)
      .catch(() => setSkills([]));
  }, []);

  if (skills.length === 0) return null;

  return (
    <div className="skill-bar">
      {skills.map((skill) => (
        <button
          key={skill.id}
          className="skill-button"
          onClick={() => onSkillClick(skill)}
          disabled={disabled}
          title={skill.description}
        >
          {skill.label}
        </button>
      ))}
    </div>
  );
}
