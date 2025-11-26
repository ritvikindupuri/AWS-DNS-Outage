import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import joblib

def train_model(data_path='dns_health_checks.csv', model_path='isolation_forest_model.joblib'):
    """
    Trains an Isolation Forest model on DNS health check data.

    Args:
        data_path (str): The path to the CSV file containing the DNS health check data.
        model_path (str): The path to save the trained model.
    """
    # Load the data
    try:
        df = pd.read_csv(data_path)
    except FileNotFoundError:
        print(f"Error: Data file not found at {data_path}")
        return

    # Feature engineering
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['hour'] = df['timestamp'].dt.hour
    features = df[['success', 'response_time', 'hour']].values

    # Scale the features
    scaler = StandardScaler()
    features_scaled = scaler.fit_transform(features)

    # Train the Isolation Forest model
    model = IsolationForest(contamination=0.05, random_state=42)
    model.fit(features_scaled)

    # Save the model and scaler
    joblib.dump((model, scaler), model_path)
    print(f"Model trained and saved to {model_path}")

if __name__ == "__main__":
    # Create a dummy dataset for training if one doesn't exist
    try:
        pd.read_csv('dns_health_checks.csv')
    except FileNotFoundError:
        print("Creating a dummy dns_health_checks.csv for training.")
        dummy_data = {
            'timestamp': pd.to_datetime(['2023-01-01 10:00:00', '2023-01-01 10:01:00', '2023-01-01 10:02:00']),
            'success': [1, 1, 0],
            'response_time': [0.1, 0.12, 5.0],
            'service': ['s3', 's3', 's3'],
            'region': ['us-east-1', 'us-east-1', 'us-east-1']
        }
        dummy_df = pd.DataFrame(dummy_data)
        dummy_df.to_csv('dns_health_checks.csv', index=False)

    train_model()
