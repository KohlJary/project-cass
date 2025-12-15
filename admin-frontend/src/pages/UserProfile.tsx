import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../context/AuthContext';
import { usersApi } from '../api/client';
import './UserProfile.css';

interface UserModel {
  user_id: string;
  display_name: string;
  background: {
    occupation?: string;
    interests?: string[];
    expertise?: string[];
    context?: string;
  };
  communication: {
    preferred_style?: string;
    formality?: string;
    detail_level?: string;
    pace?: string;
  };
  preferences: {
    topics_of_interest?: string[];
    avoid_topics?: string[];
    notification_preferences?: string;
  };
  relationship: string;
}

interface UserObservation {
  id: string;
  content: string;
  category: string;
  confidence: number;
  created_at: string;
  updated_at: string;
}

export function UserProfile() {
  const { user } = useAuth();
  const userId = user?.user_id;

  const { data: userModel, isLoading: modelLoading, error: modelError } = useQuery({
    queryKey: ['userModel', userId],
    queryFn: () => usersApi.getUserModel(userId!).then(res => res.data as UserModel),
    enabled: !!userId,
  });

  const { data: observationsData, isLoading: obsLoading } = useQuery({
    queryKey: ['userObservations', userId],
    queryFn: () => usersApi.getObservations(userId!).then(res => res.data),
    enabled: !!userId,
  });

  const observations = observationsData?.observations as UserObservation[] | undefined;

  if (modelLoading || obsLoading) {
    return (
      <div className="user-profile-page">
        <div className="loading-state">Loading your profile...</div>
      </div>
    );
  }

  if (modelError) {
    return (
      <div className="user-profile-page">
        <div className="error-state">Failed to load profile</div>
      </div>
    );
  }

  return (
    <div className="user-profile-page">
      <div className="profile-header">
        <div className="profile-avatar">
          {user?.display_name?.charAt(0).toUpperCase() || '?'}
        </div>
        <div className="profile-info">
          <h1>{user?.display_name}</h1>
          <p className="profile-subtitle">Your profile as understood by Cass</p>
        </div>
      </div>

      <div className="profile-sections">
        {/* Background Section */}
        <section className="profile-section">
          <h2>Background</h2>
          <div className="section-content">
            {userModel?.background?.occupation && (
              <div className="info-row">
                <span className="label">Occupation</span>
                <span className="value">{userModel.background.occupation}</span>
              </div>
            )}
            {userModel?.background?.interests && userModel.background.interests.length > 0 && (
              <div className="info-row">
                <span className="label">Interests</span>
                <div className="tag-list">
                  {userModel.background.interests.map((interest, i) => (
                    <span key={i} className="tag">{interest}</span>
                  ))}
                </div>
              </div>
            )}
            {userModel?.background?.expertise && userModel.background.expertise.length > 0 && (
              <div className="info-row">
                <span className="label">Expertise</span>
                <div className="tag-list">
                  {userModel.background.expertise.map((exp, i) => (
                    <span key={i} className="tag tag-expertise">{exp}</span>
                  ))}
                </div>
              </div>
            )}
            {userModel?.background?.context && (
              <div className="info-row">
                <span className="label">Context</span>
                <span className="value">{userModel.background.context}</span>
              </div>
            )}
            {!userModel?.background?.occupation && !userModel?.background?.interests?.length &&
             !userModel?.background?.expertise?.length && !userModel?.background?.context && (
              <p className="empty-state">No background information yet. Keep chatting with Cass!</p>
            )}
          </div>
        </section>

        {/* Communication Style */}
        <section className="profile-section">
          <h2>Communication Style</h2>
          <div className="section-content">
            {userModel?.communication?.preferred_style && (
              <div className="info-row">
                <span className="label">Style</span>
                <span className="value">{userModel.communication.preferred_style}</span>
              </div>
            )}
            {userModel?.communication?.formality && (
              <div className="info-row">
                <span className="label">Formality</span>
                <span className="value">{userModel.communication.formality}</span>
              </div>
            )}
            {userModel?.communication?.detail_level && (
              <div className="info-row">
                <span className="label">Detail Level</span>
                <span className="value">{userModel.communication.detail_level}</span>
              </div>
            )}
            {userModel?.communication?.pace && (
              <div className="info-row">
                <span className="label">Pace</span>
                <span className="value">{userModel.communication.pace}</span>
              </div>
            )}
            {!userModel?.communication?.preferred_style && !userModel?.communication?.formality &&
             !userModel?.communication?.detail_level && !userModel?.communication?.pace && (
              <p className="empty-state">Communication preferences will be learned over time.</p>
            )}
          </div>
        </section>

        {/* Relationship */}
        {userModel?.relationship && (
          <section className="profile-section">
            <h2>Relationship</h2>
            <div className="section-content">
              <p className="relationship-text">{userModel.relationship}</p>
            </div>
          </section>
        )}

        {/* Observations */}
        <section className="profile-section">
          <h2>Cass's Observations About You</h2>
          <div className="section-content">
            {observations && observations.length > 0 ? (
              <div className="observations-list">
                {observations.map((obs) => (
                  <div key={obs.id} className="observation-item">
                    <div className="observation-header">
                      <span className={`category-badge category-${obs.category}`}>
                        {obs.category}
                      </span>
                      <span className="confidence">
                        {Math.round(obs.confidence * 100)}% confidence
                      </span>
                    </div>
                    <p className="observation-content">{obs.content}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="empty-state">
                Cass hasn't made any observations yet. As you chat more, she'll build
                an understanding of who you are.
              </p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
